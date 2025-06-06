import os
import logging
import httpx
import asyncio
from fastapi import FastAPI, HTTPException, Body
from typing import Dict
from uuid import uuid4

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MASTER - %(levelname)s - %(message)s')

app = FastAPI()

# Use a dictionary for messages to ensure order and allow deduplication
messages: Dict[int, Dict] = {}
message_counter = 0

secondary_hosts_str = os.getenv("SECONDARY_HOSTS", "")
SECONDARY_HOSTS = secondary_hosts_str.split(',') if secondary_hosts_str else []
logging.info(f"Initialized with secondaries: {SECONDARY_HOSTS}")

@app.post("/messages")
async def append_message(payload: Dict = Body(...)):
    global message_counter
    
    message_text = payload.get("message")
    write_concern = payload.get("w", len(SECONDARY_HOSTS) + 1) # Default to all

    if not message_text:
        raise HTTPException(status_code=400, detail="Message field is required.")
    if not isinstance(write_concern, int) or write_concern < 1 or write_concern > len(SECONDARY_HOSTS) + 1:
        raise HTTPException(status_code=400, detail=f"Invalid write concern 'w'. Must be between 1 and {len(SECONDARY_HOSTS) + 1}.")

    message_counter += 1
    message_id = str(uuid4())
    seq_num = message_counter
    
    new_message = {
        "id": message_id,
        "seq": seq_num,
        "text": message_text
    }
    
    logging.info(f"Received message '{message_text}' (Seq: {seq_num}). Write Concern W={write_concern}.")
    
    # Add to master's log first (w=1 is always met)
    messages[seq_num] = new_message
    acks_needed = write_concern - 1
    
    ack_count = 0

    async def replicate(host, msg):
        nonlocal ack_count
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"http://{host}/replicate", json=msg, timeout=10.0)
                ack_count += 1
                logging.info(f"ACK received from {host} for Seq {msg['seq']}. Total ACKs: {ack_count}")
        except Exception as e:
            logging.warning(f"Failed to replicate to {host}: {e}. This secondary might be down or slow.")

    # Send replication requests concurrently
    replication_futures = [asyncio.create_task(replicate(host, new_message)) for host in SECONDARY_HOSTS]
    
    if acks_needed <= 0:
        logging.info("W=1, responding to client immediately.")
        return {"status": "Message appended to master.", "message": new_message}

    # Wait for enough ACKs
    for future in replication_futures:
        await future
        if ack_count >= acks_needed:
            logging.info(f"Write concern W={write_concern} met with {ack_count} ACKs. Responding to client.")
            # Note: Other replication tasks might still be running in the background
            return {"status": f"Message replicated with W={write_concern}.", "message": new_message}
            
    # This part is reached if not enough secondaries responded in time
    raise HTTPException(status_code=500, detail=f"Failed to meet write concern W={write_concern}. Received only {ack_count} ACKs.")


@app.get("/messages")
async def get_messages():
    # Return messages sorted by sequence number
    sorted_messages = [msg for seq, msg in sorted(messages.items())]
    return {"messages": sorted_messages}