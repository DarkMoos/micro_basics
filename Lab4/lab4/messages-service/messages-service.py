from flask import Flask, request, jsonify
from kafka import KafkaConsumer
from tenacity import retry, stop_after_attempt, wait_fixed
import os
import socket
import logging
import json
import threading

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
instance = socket.gethostname()

# Локальне сховище повідомлень
messages = []

# Отримання адрес Kafka із змінної середовища
kafka_bootstrap_servers = os.environ.get(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka1:9092,kafka2:9093,kafka3:9094"
).split(',')

# Ініціалізація Kafka Consumer з повторними спробами
@retry(stop=stop_after_attempt(5), wait=wait_fixed(5))
def create_kafka_consumer():
    logger.info(f"[{instance}] Attempting to connect to Kafka")
    return KafkaConsumer(
        'messages-topic',
        bootstrap_servers=kafka_bootstrap_servers,
        auto_offset_reset='earliest',
        group_id='messages-group',  # Однакова група для всіх екземплярів
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        max_poll_records=100,
        session_timeout_ms=30000,  # Збільшено для стабільності
        heartbeat_interval_ms=10000,  # Збільшено для стабільності
        max_poll_interval_ms=600000  # Збільшено для уникнення таймаутів
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
    for message in consumer:
        msg = message.value
        messages.append(msg)
        logger.info(f"[{instance}] Received message: {msg['txt']} with ID {msg['id']}")

# Запуск споживача в окремому потоці
threading.Thread(target=consume_messages, daemon=True).start()

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
    port = int(os.environ.get('PORT', 8882))
    logger.info(f"[{instance}] Starting on port {port}")
    app.run(host='0.0.0.0', port=port)
