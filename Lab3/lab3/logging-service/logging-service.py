import os
import socket
import hazelcast
from flask import Flask, request, jsonify
import logging
import time

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
instance = socket.gethostname()

# Отримання адрес Hazelcast із змінних середовища
hazelcast_members = os.environ.get("HZ_ADDRESS", "hazelcast1:5701,hazelcast2:5701,hazelcast3:5701").split(',')

# Додаємо затримку перед підключенням
time.sleep(5)  # Дозволяємо Hazelcast-нодам запуститися

try:
    # Ініціалізація клієнта Hazelcast
    client = hazelcast.HazelcastClient(
        cluster_name="dev",
        cluster_members=hazelcast_members,
        reconnect_mode="ASYNC"
    )
    msg_map = client.get_map("messages").blocking()
    logger.info(f"[{instance}] Connected to Hazelcast cluster")
except Exception as e:
    logger.error(f"[{instance}] Failed to connect to Hazelcast: {str(e)}")
    raise

@app.route('/logging', methods=['POST', 'GET'])
def handle_logging():
    logger.info(f"[{instance}] Received request: {request.method} {request.url}")
    if request.method == 'POST':
        id = request.form.get('id')
        txt = request.form.get('txt')
        if not (id and txt):
            logger.warning(f"[{instance}] Invalid request: No id or text")
            return jsonify({'error': 'No id or text'}), 400

        if msg_map.contains_key(id):
            logger.info(f"[{instance}] Duplicate message detected: {id}")
            return jsonify({'message': 'Duplicate detected'}), 200

        try:
            msg_map.put(id, f"{txt} (processed by {instance})")
            logger.info(f"[{instance}] Logged message: {txt} with ID {id}")
            return jsonify({'message': 'Message logged', 'id': id}), 201
        except Exception as e:
            logger.error(f"[{instance}] Failed to log message {id}: {str(e)}")
            return jsonify({'error': str(e)}), 500

    elif request.method == 'GET':
        try:
            all_messages = list(msg_map.values())
            logger.info(f"[{instance}] Retrieved {len(all_messages)} messages")
            return jsonify({
                'instance': instance,
                'messages': all_messages
            }), 200
        except Exception as e:
            logger.error(f"[{instance}] Failed to retrieve messages: {str(e)}")
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 9001))
    logger.info(f"[{instance}] Starting on port {port}")
    app.run(host='0.0.0.0', port=port)
