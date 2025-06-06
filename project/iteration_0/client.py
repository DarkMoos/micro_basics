import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SERVER_URL = "http://127.0.0.1:8000"

def send_message(message: str):
    """
    Sends a message to the server.
    """
    try:
        response = requests.post(SERVER_URL, json={"message": message})
        response.raise_for_status()  # Raise an exception for bad status codes
        logging.info(f"Server response: {response.json()}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Could not connect to the server: {e}")

if __name__ == "__main__":
    print("Enter your message and press Enter to send. Type 'exit' to quit.")
    while True:
        user_input = input("Your message: ")
        if user_input.lower() == 'exit':
            break
        send_message(user_input)