import logging
import asyncio
from fastapi import FastAPI, Request, HTTPException
from typing import List
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - SECONDARY - %(levelname)s - %(message)s')

app = FastAPI()

replicated_messages: List[str] = []

REPLICATION_DELAY_SECONDS = int(os.getenv("REPLICATION_DELAY_SECONDS", 0))

@app.post("/replicate")
async def replicate_message(request: Request):
    data = await request.json()
    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="Message not provided for replication.")

    logging.info(f"Received replication request for message: '{message}'. Applying {REPLICATION_DELAY_SECONDS}s delay...")
    await asyncio.sleep(REPLICATION_DELAY_SECONDS)
    
    replicated_messages.append(message)
    logging.info(f"Successfully replicated message: '{message}'. Sending ACK.")
    return {"status": "Message replicated successfully."}

@app.get("/messages")
async def get_replicated_messages():
    logging.info("Returning all replicated messages.")
    return {"messages": replicated_messages}