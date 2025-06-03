from flask import Flask, request, jsonify
from kafka import KafkaConsumer
from tenacity import retry, stop_after_attempt, wait_fixed
import os
import socket
import logging
import json
import threading
import consul
import uuid
import time

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
instance = socket.gethostname()
port = int(os.environ.get('PORT', 8882))
consul_address = os.environ.get('CONSUL_ADDRESS', 'http://consul:8500')

# Ініціалізація Consul клієнта
consul_client = consul.Consul(host='consul', port=8500)

# Реєстрація сервісу в Consul
service_id = f"messages-{instance}-{port}"
consul_client.agent.service.register(
    name="messages-service",
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

# Локальне сховище повідомлень
messages = []

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

# Ініціалізація Kafka Consumer з повторними спробами
@retry(stop=stop_after_attempt(5), wait=wait_fixed(5))
def create_kafka_consumer():
    logger.info(f"[{instance}] Attempting to connect to Kafka")
    return KafkaConsumer(
        kafka_topic,
        bootstrap_servers=kafka_bootstrap_servers,
        auto_offset_reset='earliest',
        group_id='messages-group',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        max_poll_records=100,
        session_timeout_ms=60000,  # Збільшено до 60 секунд
        heartbeat_interval_ms=3000,  # Зменшено до 3 секунд
        max_poll_interval_ms=900000,  # Збільшено до 15 хвилин
        request_timeout_ms=305000,  # Додано для уникнення тайм-аутів
        connections_max_idle_ms=540000  # 9 хвилин
    )

try:
    consumer = create_kafka_consumer()
    logger.info(f"[{instance}] Connected to Kafka")
except Exception as e:
    logger.error(f"[{instance}] Failed to connect to Kafka after retries: {str(e)}")
    raise

# Функція для асинхронного вичитування повідомлень із Kafka
def consume_messages():
    logger.info(f"[{instance}] Starting Kafka consumer")
    while True:
        try:
            for message in consumer:
                msg = message.value
                messages.append(msg)
                logger.info(f"[{instance}] Received message: {msg['txt']} with ID {msg['id']}")
                consumer.commit()  # Явний коміт після обробки
        except Exception as e:
            logger.error(f"[{instance}] Error in Kafka consumer: {str(e)}")
            time.sleep(5)  # Затримка перед повторною спробою

# Запуск споживача в окремому потоці
threading.Thread(target=consume_messages, daemon=True).start()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/messages', methods=['GET'])
def get_messages():
    try:
        message_id = request.args.get('id')
        if message_id:
            for msg in messages:
                if msg['id'] == message_id:
                    return jsonify({'id': message_id, 'text': msg['txt']})
            logger.warning(f"[{instance}] Message with ID {message_id} not found")
            return jsonify({'error': 'Message not found'}), 404

        logger.info(f"[{instance}] Retrieved {len(messages)} messages")
        return jsonify([{'id': msg['id'], 'text': msg['txt']} for msg in messages])
    except Exception as e:
        logger.error(f"[{instance}] Failed to retrieve messages: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info(f"[{instance}] Starting on port {port}")
    app.run(host='0.0.0.0', port=port)
