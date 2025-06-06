import requests
import time

MASTER_URL = "http://localhost:8000"
SECONDARY1_URL = "http://localhost:9001"
SECONDARY2_URL = "http://localhost:9002"

def post_message(msg, w):
    print(f"\n---> Sending message: '{msg}' with W={w}")
    start_time = time.time()
    try:
        response = requests.post(f"{MASTER_URL}/messages", json={"message": msg, "w": w})
        response.raise_for_status()
        end_time = time.time()
        print(f"Response from master: {response.json()}")
        print(f"Request took {end_time - start_time:.2f} seconds.")
    except requests.RequestException as e:
        print(f"Error posting message: {e}")

def get_messages(name, url):
    print(f"\n<--- Getting messages from {name} ({url})")
    try:
        response = requests.get(f"{url}/messages")
        print(f"{name} messages: {response.json()}")
    except requests.RequestException as e:
        print(f"Error getting messages from {name}: {e}")

def check_all_nodes():
    get_messages("Master", MASTER_URL)
    get_messages("Secondary-1", SECONDARY1_URL)
    get_messages("Secondary-2", SECONDARY2_URL)

if __name__ == "__main__":
    print("--- Test 1: W=2 (should be fast, waits for faster secondary) ---")
    post_message("Msg1", w=2)
    
    print("\n--- Checking nodes immediately (expect inconsistency) ---")
    # Secondary 2 is slow, so it won't have the message yet
    check_all_nodes()

    print("\n--- Waiting 5 seconds for slow secondary to catch up... ---")
    time.sleep(5)
    
    print("\n--- Checking nodes again (expect consistency) ---")
    check_all_nodes()

    print("\n\n--- Test 2: W=3 (should be slow, waits for both secondaries) ---")
    post_message("Msg2", w=3)
    check_all_nodes()

    post_message("Msg1", w=1)
    post_message("Msg2", w=2)
    check_all_nodes()
    # wait 5s 
    check_all_nodes()
    post_message("Msg2", w=3)
    check_all_nodes()