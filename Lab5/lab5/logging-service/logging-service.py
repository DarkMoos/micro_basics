from flask import Flask, request, jsonify
import hazelcast
import os
import socket
import logging
import consul
import uuid
import requests

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
instance = socket.gethostname()
port = int(os.environ.get('PORT', 50051))
consul_address = os.environ.get('CONSUL_ADDRESS', 'http://consul:8500')

# Ініціалізація Consul клієнта
consul_client = consul.Consul(host='consul', port=8500)

# Реєстрація сервісу в Consul
service_id = f"logging-{instance}-{port}"
consul_client.agent.service.register(
    name="logging-service",
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

# Отримання конфігурації Hazelcast із Consul
def get_hazelcast_config():
    try:
        _, config = consul_client.kv.get('hazelcast/config')
        if config and 'Value' in config:
            hz_addresses = config['Value'].decode('utf-8').split(',')
            logger.info(f"[{instance}] Fetched Hazelcast config: {hz_addresses}")
            return hz_addresses
        else:
            logger.error(f"[{instance}] No Hazelcast config found in Consul")
            raise Exception("Hazelcast config not found")
    except Exception as e:
        logger.error(f"[{instance}] Failed to fetch Hazelcast config: {str(e)}")
        raise

hz_addresses = get_hazelcast_config()
client = hazelcast.HazelcastClient(cluster_name="dev", cluster_members=hz_addresses)
messages_map = client.get_map("messages").blocking()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/logging', methods=['POST'])
def log_message():
    try:
        data = request.get_json()
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
    logger.info(f"[{instance}] Starting on port {port}")
    app.run(host='0.0.0.0', port=port)
