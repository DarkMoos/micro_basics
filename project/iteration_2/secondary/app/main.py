import logging
import asyncio
import os
from fastapi import FastAPI, Request, HTTPException
from typing import Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - SECONDARY - %(levelname)s - %(message)s')

app = FastAPI()

replicated_messages: Dict[int, Dict] = {}
# Get a unique identifier for this secondary to simulate different delays
SECONDARY_ID = os.getenv("SECONDARY_ID", "default")
# Make one secondary slower than the other
REPLICATION_DELAY_SECONDS = int(os.getenv("REPLICATION_DELAY_SECONDS", 0))
@app.post("/replicate")
async def replicate_message(request: Request):
    data = await request.json()
    message_id = data.get("id")
    seq_num = data.get("seq")
    
    if not all([message_id, seq_num]):
        raise HTTPException(status_code=400, detail="Invalid message format.")
    
    # Deduplication check
    if any(msg['id'] == message_id for msg in replicated_messages.values()):
        logging.warning(f"Duplicate message received (ID: {message_id}). Ignoring.")
        return {"status": "Duplicate message ignored."}

    logging.info(f"Received replication request for Seq {seq_num}. Applying {REPLICATION_DELAY_SECONDS}s delay...")
    await asyncio.sleep(REPLICATION_DELAY_SECONDS)
    
    replicated_messages[seq_num] = data
    logging.info(f"Successfully replicated message (Seq: {seq_num}).")
    return {"status": "Message replicated."}

@app.get("/messages")
async def get_replicated_messages():
    # Return messages sorted by sequence number for total order
    sorted_messages = [msg for seq, msg in sorted(replicated_messages.items())]
    return {"messages": sorted_messages}