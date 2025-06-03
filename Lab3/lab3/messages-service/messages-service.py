from flask import Flask, request, jsonify
import hazelcast
import os
import logging
import time

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Отримання адрес Hazelcast із змінних середовища
hazelcast_members = os.environ.get(
    "HZ_CLUSTER_MEMBERS",
    "hazelcast1:5701,hazelcast2:5701,hazelcast3:5701"
).split(',')

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
    logger.info("Connected to Hazelcast cluster")
except Exception as e:
    logger.error(f"Failed to connect to Hazelcast: {str(e)}")
    raise

@app.route('/messages', methods=['GET'])
def get_messages():
    try:
        # Фільтрація за параметром 'id' (опціонально)
        message_id = request.args.get('id')
        if message_id:
            if msg_map.contains_key(message_id):
                message = msg_map.get(message_id)
                return jsonify({'id': message_id, 'text': message})
            else:
                logger.warning(f"Message with ID {message_id} not found")
                return jsonify({'error': 'Message not found'}), 404

        # Отримання всіх повідомлень, якщо id не вказано
        entries = msg_map.entry_set()
        result = [{'id': key, 'text': value} for key, value in entries]
        logger.info(f"Retrieved {len(result)} messages")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Failed to retrieve messages: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8882)
