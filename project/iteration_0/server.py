import logging
from fastapi import FastAPI, Request

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

@app.post("/")
async def receive_message(request: Request):
    """
    Receives a message from a client and logs it to the server console.
    """
    data = await request.json()
    message = data.get("message")
    
    if message:
        logging.info(f"Received message: '{message}'")
        return {"status": "Message received successfully!"}
    else:
        logging.warning("Received request with no message.")
        return {"status": "No message provided."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)