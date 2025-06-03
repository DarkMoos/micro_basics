import requests
import uuid
import random
import os
from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, wait_fixed
import logging

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Адреса config-server із змінної середовища
config_server = os.environ.get("CONFIG_SERVER_ADDRESS", "http://config-server:8881")

# Функція для отримання адрес сервісів із config-server
def get_service_addresses(service_name):
    logger.info(f"Fetching addresses for {service_name} from {config_server}")
    try:
        response = requests.get(f"{config_server}/services/{service_name}", timeout=3)
        if response.status_code == 200:
            addresses = response.json().get("addresses", [])
            logger.info(f"Received addresses for {service_name}: {addresses}")
            return addresses
        else:
            logger.error(f"Config-server returned status {response.status_code} for {service_name}")
            raise Exception(f"Failed to get addresses for {service_name}")
    except Exception as e:
        logger.error(f"Error fetching addresses for {service_name}: {str(e)}")
        return []

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def send_with_retry(services, data):
    tried = set()
    while len(tried) < len(services):
        service = random.choice(services)
        if service in tried:
            continue
        tried.add(service)
        try:
            logger.info(f"Trying to send to {service}")
            response = requests.post(service, data=data, timeout=3)
            if response.status_code == 201:
                logger.info(f"Successfully sent to {service}")
                return response
        except Exception as e:
            logger.error(f"Failed to send to {service}: {str(e)}")
            continue
    raise Exception('All logging services failed.')

@app.route('/messages', methods=['POST', 'GET'])
def handle_messages():
    if request.method == 'POST':
        txt = request.form.get('txt')
        if not txt:
            logger.warning("No message provided")
            return jsonify({'error': 'No message provided'}), 400
        id = str(uuid.uuid4())
        msg = {'id': id, 'txt': txt}

        # Отримуємо адреси logging-service із config-server
        logging_services = get_service_addresses("logging")
        if not logging_services:
            logger.error("No logging services available")
            return jsonify({'error': 'No logging services available'}), 503

        try:
            send_with_retry(logging_services, msg)
            return jsonify(msg), 200
        except Exception as e:
            logger.error(f"Failed to process POST request: {str(e)}")
            return jsonify({'error': str(e)}), 500

    elif request.method == 'GET':
        # Отримуємо адреси logging-service і messages-service
        logging_services = get_service_addresses("logging")
        messages_services = get_service_addresses("messages")

        results = []
        for service in logging_services:
            try:
                logger.info(f"Fetching from {service}")
                r = requests.get(service, timeout=3)
                data = r.json()
                results.append({
                    'service': service,
                    'instance': data.get('instance'),
                    'messages': data.get('messages')
                })
            except Exception as e:
                logger.error(f"Failed to fetch from {service}: {str(e)}")
                results.append({
                    'service': service,
                    'error': str(e)
                })

        # Отримуємо всі повідомлення з messages-service
        all_msgs = []
        for messages_service in messages_services:
            try:
                logger.info(f"Fetching all messages from {messages_service}")
                r = requests.get(messages_service, timeout=3)
                all_msgs = r.json()
                break  # Використовуємо перший доступний messages-service
            except Exception as e:
                logger.error(f"Failed to fetch from {messages_service}: {str(e)}")
                all_msgs = {'error': str(e)}

        return jsonify({
            'logging_services': results,
            'all_messages_from_hazelcast': all_msgs
        }), 200

if __name__ == '__main__':
    logger.info("Starting facade-service on port 8880")
    app.run(host='0.0.0.0', port=8880)
