from flask import Flask, request, jsonify
import hazelcast
import os
import socket
import logging

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
instance = socket.gethostname()

# Підключення до Hazelcast
hz_addresses = os.environ.get("HZ_ADDRESS", "hazelcast1:5701,hazelcast2:5701,hazelcast3:5701").split(',')
client = hazelcast.HazelcastClient(cluster_name="dev", cluster_members=hz_addresses)
messages_map = client.get_map("messages").blocking()

@app.route('/logging', methods=['POST'])
def log_message():
    try:
        data = request.get_json()  # Очікуємо JSON
        if not data or 'id' not in data or 'txt' not in data:
            logger.warning(f"[{instance}] Invalid message format")
            return jsonify({'error': 'Invalid message format'}), 400
        msg_id = data['id']
        msg_txt = data['txt']
        messages_map.put(msg_id, f"{msg_txt} (processed by {instance})")
        logger.info(f"[{instance}] Logged message: {msg_txt} with ID {msg_id}")
        return jsonify({'status': 'logged'}), 201
    except Exception as e:
        logger.error(f"[{instance}] Failed to log message: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/logging', methods=['GET'])
def get_messages():
    try:
        messages = list(messages_map.values())
        logger.info(f"[{instance}] Retrieved {len(messages)} messages")
        return jsonify({
            'instance': instance,
            'messages': messages
        })
    except Exception as e:
        logger.error(f"[{instance}] Failed to retrieve messages: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 50051))
    logger.info(f"[{instance}] Starting on port {port}")
    app.run(host='0.0.0.0', port=port)
