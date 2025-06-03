import requests
import uuid
import random
import os
from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, wait_fixed
from kafka import KafkaProducer
import json
import logging

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Адреса config-server із змінної середовища
config_server = os.environ.get("CONFIG_SERVER_ADDRESS", "http://config-server:8881")

# Kafka producer з повторними спробами
kafka_bootstrap_servers = os.environ.get(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka1:9092,kafka2:9093,kafka3:9094"
).split(',')

@retry(stop=stop_after_attempt(5), wait=wait_fixed(5))
def create_kafka_producer():
    logger.info("Attempting to connect to Kafka")
    return KafkaProducer(
        bootstrap_servers=kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        retries=5,
        max_block_ms=10000
    )

try:
    producer = create_kafka_producer()
    logger.info("Connected to Kafka")
except Exception as e:
    logger.error(f"Failed to connect to Kafka after retries: {str(e)}")
    raise

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
    errors = []
    while len(tried) < len(services):
        service = random.choice(services)
        if service in tried:
            continue
        tried.add(service)
        try:
            logger.info(f"Trying to send to {service}")
            response = requests.post(service, json=data, timeout=3)  # Змінено на JSON
            if response.status_code == 201:
                logger.info(f"Successfully sent to {service}")
                return response
        except Exception as e:
            errors.append(f"Failed to send to {service}: {str(e)}")
            continue
    logger.error(f"All services failed: {errors}")
    raise Exception(f"All logging services failed: {errors}")

@app.route('/messages', methods=['POST', 'GET'])
def handle_messages():
    if request.method == 'POST':
        txt = request.form.get('txt')
        if not txt:
            logger.warning("No message provided")
            return jsonify({'error': 'No message provided'}), 400
        id = str(uuid.uuid4())
        msg = {'id': id, 'txt': txt}

        # Відправка до logging-service
        logging_services = get_service_addresses("logging")
        if not logging_services:
            logger.error("No logging services available")
            return jsonify({'error': 'No logging services available'}), 503

        try:
            send_with_retry(logging_services, msg)
        except Exception as e:
            logger.error(f"Failed to process logging-service POST: {str(e)}")
            return jsonify({'error': str(e)}), 500

        # Відправка до Kafka
        try:
            producer.send('messages-topic', msg)
            producer.flush()
            logger.info(f"Sent message to Kafka: {msg}")
        except Exception as e:
            logger.error(f"Failed to send to Kafka: {str(e)}")
            return jsonify({'error': str(e)}), 500

        return jsonify(msg), 200

    elif request.method == 'GET':
        logging_services = get_service_addresses("logging")
        messages_services = get_service_addresses("messages")

        # Збір повідомлень із logging-service (достатньо одного, бо вони синхронізовані через Hazelcast)
        logging_results = []
        if logging_services:
            selected_logging_service = random.choice(logging_services)
            try:
                logger.info(f"Fetching from {selected_logging_service}")
                r = requests.get(selected_logging_service, timeout=3)
                data = r.json()
                logging_results.append({
                    'service': selected_logging_service,
                    'instance': data.get('instance'),
                    'messages': data.get('messages')
                })
            except Exception as e:
                logger.error(f"Failed to fetch from {selected_logging_service}: {str(e)}")
                logging_results.append({
                    'service': selected_logging_service,
                    'error': str(e)
                })

        # Збір повідомлень із усіх messages-service
        all_messages = {}
        for service in messages_services:
            try:
                logger.info(f"Fetching messages from {service}")
                r = requests.get(service, timeout=3)
                messages = r.json()
                for msg in messages:
                    all_messages[msg['id']] = {'id': msg['id'], 'text': msg['text']}
            except Exception as e:
                logger.error(f"Failed to fetch from {service}: {str(e)}")

        # Збір повідомлень із logging-service
        logging_messages = {}
        for result in logging_results:
            if 'messages' in result:
                for msg_text in result['messages']:
                    # Витягуємо ID і текст із формату "msgX (processed by instance)"
                    try:
                        msg_id = msg_text.split(' (processed by')[0]
                        msg_id = next((m['id'] for m in all_messages.values() if m['text'] == msg_id), None)
                        if msg_id:
                            logging_messages[msg_id] = {'id': msg_id, 'text': msg_text.split(' (')[0]}
                    except Exception as e:
                        logger.error(f"Failed to parse logging message {msg_text}: {str(e)}")

        # Об'єднання повідомлень
        combined_messages = {}
        for msg in all_messages.values():
            combined_messages[msg['id']] = msg
        for msg in logging_messages.values():
            combined_messages[msg['id']] = msg

        return jsonify({
            'logging_services': logging_results,
            'all_messages_from_messages_service': list(all_messages.values()),
            'combined_messages': list(combined_messages.values())
        }), 200

if __name__ == '__main__':
    logger.info("Starting facade-service on port 8880")
    app.run(host='0.0.0.0', port=8880)
