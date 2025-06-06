import os
import logging
import httpx
import asyncio
from fastapi import FastAPI, Request, HTTPException, Body, BackgroundTasks
from typing import List, Dict
from uuid import uuid4

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MASTER - %(levelname)s - %(message)s')
app = FastAPI()

# Use a dictionary for messages to ensure order and allow deduplication
messages: Dict[int, Dict] = {}
message_counter = 0
replication_status: Dict[int, asyncio.Event] = {} # Tracks status for each secondary
secondary_health: Dict[str, bool] = {} # Tracks health of secondaries

secondary_hosts_str = os.getenv("SECONDARY_HOSTS", "")
SECONDARY_HOSTS = secondary_hosts_str.split(',') if secondary_hosts_str else []
for host in SECONDARY_HOSTS:
    secondary_health[host] = True # Assume healthy at start
logging.info(f"Initialized with secondaries: {SECONDARY_HOSTS}")

# --- BACKGROUND REPLICATION & RETRIES ---
async def replicate_to_secondary(host: str, message: Dict):
    """Replicates a single message to a single secondary with progressive timeouts."""
    max_delay = 32
    delay = 1
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"http://{host}/replicate", json=message, timeout=5.0)
                response.raise_for_status()
                if not secondary_health.get(host, False):
                    logging.info(f"Secondary {host} is back online. Re-syncing old messages.")
                    asyncio.create_task(resync_secondary(host)) # Re-sync in the background
                secondary_health[host] = True
                logging.info(f"Successfully replicated Seq {message['seq']} to {host}.")
                # Signal that this specific replication is done
                if host in replication_status and message['seq'] in replication_status[host]:
                    replication_status[host][message['seq']].set()
                return
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            secondary_health[host] = False
            logging.error(f"Failed to replicate Seq {message['seq']} to {host}. Error: {e}. Retrying in {delay}s.")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay) # Exponential backoff with a cap

async def resync_secondary(host: str):
    """Sends all missed messages to a newly available secondary."""
    logging.info(f"Starting resync process for {host}...")
    # This is a simplified resync. A real implementation would query the secondary
    # for its last known sequence number.
    sorted_messages = [msg for seq, msg in sorted(messages.items())]
    for msg in sorted_messages:
        await replicate_to_secondary(host, msg)
    logging.info(f"Resync process for {host} complete.")

# --- API ENDPOINTS ---
@app.post("/messages")
async def append_message(background_tasks: BackgroundTasks, payload: Dict = Body(...)):
    global message_counter
    
    message_text = payload.get("message")
    write_concern = payload.get("w", len(SECONDARY_HOSTS) + 1)
    
    if not message_text: raise HTTPException(400, "Message field required.")
    if not isinstance(write_concern, int) or write_concern < 1: raise HTTPException(400, f"Invalid write concern 'w'.")

    message_counter += 1
    seq_num = message_counter
    new_message = {"id": str(uuid4()), "seq": seq_num, "text": message_text}
    
    logging.info(f"Received '{message_text}' (Seq: {seq_num}), W={write_concern}. Storing locally.")
    messages[seq_num] = new_message
    
    # Immediately start background replication for all secondaries
    for host in SECONDARY_HOSTS:
        background_tasks.add_task(replicate_to_secondary, host, new_message)

    # Wait for the required number of ACKs
    acks_needed = write_concern - 1
    if acks_needed <= 0:
        return {"status": "Message stored on master.", "message": new_message}

    # Asynchronously wait for ACKs from healthy secondaries
    ack_wait_tasks = []
    # live_secondaries = [host for host in SECONDARY_HOSTS if secondary_health.get(host, True)]
    
    # if len(live_secondaries) < acks_needed:
    #     raise HTTPException(status_code=503, detail=f"Not enough secondaries available ({len(live_secondaries)}) to meet write concern W={write_concern}.")

    async def wait_for_ack(host, msg):
        try:
            # We don't need the full retry logic here, just one attempt for the client response
            async with httpx.AsyncClient() as client:
                await client.post(f"http://{host}/replicate", json=msg, timeout=10.0)
            return True
        except Exception:
            return False

    # Fire off requests to live secondaries and wait for the first `acks_needed` to complete
    wait_tasks = [wait_for_ack(host, new_message) for host in SECONDARY_HOSTS]
    # wait_tasks = [wait_for_ack(host, new_message) for host in live_secondaries]
    acks_received = 0
    for future in asyncio.as_completed(wait_tasks):
        if await future:
            acks_received += 1
            if acks_received >= acks_needed:
                logging.info(f"Write concern W={write_concern} met for Seq {seq_num}. Responding to client.")
                return {"status": f"Message replicated with W={write_concern}.", "message": new_message}
    
    # If we exit the loop, it means we couldn't get enough ACKs even from "live" secondaries
    raise HTTPException(status_code=504, detail=f"Timed out waiting for {acks_needed} ACKs. Got {acks_received}.")


@app.get("/messages")
async def get_messages():
    # Return messages sorted by sequence number
    sorted_messages = [msg for seq, msg in sorted(messages.items())]
    return {"messages": sorted_messages}

@app.on_event("startup")
async def startup_event():
    # Initialize replication status tracking
    global replication_status
    for host in SECONDARY_HOSTS:
        replication_status[host] = {}