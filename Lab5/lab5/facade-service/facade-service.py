import socket
import requests
import uuid
import random
import os
from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, wait_fixed
from kafka import KafkaProducer
import json
import logging
import consul

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
instance = socket.gethostname()
port = 8880
consul_address = os.environ.get('CONSUL_ADDRESS', 'http://consul:8500')

# Ініціалізація Consul клієнта
consul_client = consul.Consul(host='consul', port=8500)

# Реєстрація сервісу в Consul
service_id = f"facade-{instance}-{port}"
consul_client.agent.service.register(
    name="facade-service",
    service_id=service_id,
    address=instance,
    port=port,
    check=consul.Check.http(
        url=f"http://{instance}:{port}/health",
        interval="10s",
        timeout="5s",
        deregister="30s"
    )
)
logger.info(f"[{instance}] Registered with Consul as {service_id}")

# Отримання конфігурації Kafka із Consul
def get_kafka_config():
    try:
        _, config = consul_client.kv.get('kafka/config')
        if config and 'Value' in config:
            kafka_config = json.loads(config['Value'].decode('utf-8'))
            logger.info(f"[{instance}] Fetched Kafka config: {kafka_config}")
            return kafka_config
        else:
            logger.error(f"[{instance}] No Kafka config found in Consul")
            raise Exception("Kafka config not found")
    except Exception as e:
        logger.error(f"[{instance}] Failed to fetch Kafka config: {str(e)}")
        raise

kafka_config = get_kafka_config()
kafka_bootstrap_servers = kafka_config.get('bootstrap_servers', 'kafka1:9092,kafka2:9093,kafka3:9094').split(',')
kafka_topic = kafka_config.get('topic', 'messages-topic')

# Kafka producer з повторними спробами
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

# Функція для отримання адрес сервісів із Consul
def get_service_addresses(service_name):
    logger.info(f"Fetching addresses for {service_name} from Consul")
    try:
        _, services = consul_client.health.service(service_name, passing=True)
        addresses = [f"http://{service['Service']['Address']}:{service['Service']['Port']}/{service_name.replace('-service', '')}"
                     for service in services]
        logger.info(f"Received addresses for {service_name}: {addresses}")
        return addresses
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
            response = requests.post(service, json=data, timeout=3)
            if response.status_code == 201:
                logger.info(f"Successfully sent to {service}")
                return response
        except Exception as e:
            errors.append(f"Failed to send to {service}: {str(e)}")
            continue
    logger.error(f"All services failed: {errors}")
    raise Exception(f"All services failed: {errors}")

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

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
        logging_services = get_service_addresses("logging-service")
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
            producer.send(kafka_topic, msg)
            producer.flush()
            logger.info(f"Sent message to Kafka: {msg}")
        except Exception as e:
            logger.error(f"Failed to send to Kafka: {str(e)}")
            return jsonify({'error': str(e)}), 500

        return jsonify(msg), 200

    elif request.method == 'GET':
        logging_services = get_service_addresses("logging-service")
        messages_services = get_service_addresses("messages-service")

        # Збір повідомлень із усіх logging-service
        logging_results = []
        for selected_logging_service in logging_services:
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
    logger.info(f"[{instance}] Starting facade-service on port {port}")
    app.run(host='0.0.0.0', port=port)
