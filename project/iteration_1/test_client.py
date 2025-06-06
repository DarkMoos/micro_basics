import requests
import time

MASTER_URL = "http://localhost:8000"

# Note: In this setup, we don't expose secondary ports to the host.
# We would need to add them to docker-compose.yml to query them directly.
# For now, we trust the master's logs.

def post_message(msg):
    print(f"\nSending message: '{msg}'...")
    start_time = time.time()
    try:
        response = requests.post(f"{MASTER_URL}/messages", json={"message": msg})
        response.raise_for_status()
        end_time = time.time()
        print(f"Response from master: {response.json()}")
        print(f"Request took {end_time - start_time:.2f} seconds.")
    except requests.RequestException as e:
        print(f"Error posting message: {e}")

def get_master_messages():
    print("\nGetting messages from master...")
    try:
        response = requests.get(f"{MASTER_URL}/messages")
        print(f"Master messages: {response.json()}")
    except requests.RequestException as e:
        print(f"Error getting messages: {e}")


if __name__ == "__main__":
    post_message("Hello World")
    get_master_messages()