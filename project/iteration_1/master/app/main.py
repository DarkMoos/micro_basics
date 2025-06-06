import os
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException
from typing import List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MASTER - %(levelname)s - %(message)s')

app = FastAPI()

# In-memory list to store messages
messages: List[str] = []

# Get secondary addresses from environment variables
secondary_hosts_str = os.getenv("SECONDARY_HOSTS", "")
SECONDARY_HOSTS = secondary_hosts_str.split(',') if secondary_hosts_str else []
logging.info(f"Initialized with secondaries: {SECONDARY_HOSTS}")

@app.post("/messages")
async def append_message(request: Request):
    data = await request.json()
    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="Message field is required.")

    logging.info(f"Received message: '{message}'. Appending to master log.")
    messages.append(message)
    
    # Replicate to all secondaries and wait for ACKs
    async with httpx.AsyncClient() as client:
        for host in SECONDARY_HOSTS:
            try:
                logging.info(f"Replicating message to {host}...")
                response = await client.post(f"http://{host}/replicate", json={"message": message}, timeout=30.0)
                response.raise_for_status()
                logging.info(f"Successfully replicated message to {host}. ACK received.")
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logging.error(f"Failed to replicate message to {host}: {e}")
                # Since replication is blocking, we fail the entire request
                raise HTTPException(status_code=500, detail=f"Failed to replicate to secondary: {host}")

    return {"status": "Message appended and replicated to all secondaries."}

@app.get("/messages")
async def get_messages():
    logging.info("Returning all messages from master.")
    return {"messages": messages}