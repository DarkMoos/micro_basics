import logging
import asyncio
import os
import random
from fastapi import FastAPI, Request, HTTPException
from typing import Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - SECONDARY - %(levelname)s - %(message)s')
app = FastAPI()

replicated_messages: Dict[int, Dict] = {}
pending_messages: Dict[int, Dict] = {} # Buffer for out-of-order messages
expected_seq_num = 1

# --- FAILURE SIMULATION ---
SHOULD_FAIL_RANDOMLY = os.getenv("FAIL_RANDOMLY", "false").lower() == "true"
FAIL_AFTER_SAVE = os.getenv("FAIL_AFTER_SAVE", "false").lower() == "true"

# --- API ENDPOINTS ---
@app.post("/replicate")
async def replicate_message(request: Request):
    global expected_seq_num
    
    data = await request.json()
    seq_num = data.get("seq")
    message_id = data.get("id")

    if not all([message_id, seq_num is not None]):
        raise HTTPException(400, "Invalid message format.")
    
    # --- TEST: Simulate random internal server error BEFORE saving
    if SHOULD_FAIL_RANDOMLY and random.random() < 0.3 and seq_num == 3: # Fail for Msg3
        logging.error(f"Simulating random failure for Seq {seq_num}.")
        raise HTTPException(500, "Simulated internal server error.")

    # --- Deduplication
    if seq_num < expected_seq_num or seq_num in replicated_messages:
        logging.warning(f"Received duplicate or old message (Seq: {seq_num}). Sending ACK and ignoring.")
        return {"status": "Duplicate message ignored."}

    # --- Total Order Logic
    if seq_num > expected_seq_num:
        logging.warning(f"Received out-of-order message. Expected {expected_seq_num}, got {seq_num}. Buffering.")
        pending_messages[seq_num] = data
        return {"status": "Message buffered."} # Still ACK to unblock master

    # --- Process current message
    replicated_messages[seq_num] = data
    logging.info(f"Successfully applied message Seq {seq_num}.")

    # --- TEST: Simulate failure AFTER saving to test master retry + secondary deduplication
    if FAIL_AFTER_SAVE and random.random() < 0.5:
        logging.error(f"Simulating failure AFTER saving Seq {seq_num}.")
        raise HTTPException(500, "Simulated failure after save.")

    # --- Process buffered messages
    expected_seq_num += 1
    while expected_seq_num in pending_messages:
        message_to_process = pending_messages.pop(expected_seq_num)
        replicated_messages[expected_seq_num] = message_to_process
        logging.info(f"Applied buffered message Seq {expected_seq_num}.")
        expected_seq_num += 1
        
    return {"status": "Message replicated and applied."}

@app.get("/health")
async def health_check():
    """A simple health check endpoint for the master to poll."""
    return {"status": "ok"}

@app.get("/messages")
async def get_replicated_messages():
    # Return messages sorted by sequence number for total order
    sorted_messages = [msg for seq, msg in sorted(replicated_messages.items())]
    return {"messages": sorted_messages, "expected_seq": expected_seq_num}