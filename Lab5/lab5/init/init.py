import consul
import json
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def wait_for_consul():
    consul_client = consul.Consul(host='consul', port=8500)
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            consul_client.status.leader()
            logger.info("Consul leader found, proceeding with initialization")
            return consul_client
        except Exception as e:
            logger.warning(f"Waiting for Consul to be ready... Attempt {attempt + 1}/{max_attempts}")
            time.sleep(2)
    raise Exception("Consul is not ready after maximum attempts")

def initialize_consul():
    try:
        consul_client = wait_for_consul()

        # Налаштування Hazelcast
        hazelcast_config = "hazelcast1:5701,hazelcast2:5701,hazelcast3:5701"
        consul_client.kv.put('hazelcast/config', hazelcast_config)
        logger.info("Hazelcast config initialized in Consul")

        # Налаштування Kafka
        kafka_config = {
            "bootstrap_servers": "kafka1:9092,kafka2:9093,kafka3:9094",
            "topic": "messages-topic"
        }
        consul_client.kv.put('kafka/config', json.dumps(kafka_config))
        logger.info("Kafka config initialized in Consul")

        logger.info("Consul key/value store initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Consul: {str(e)}")
        raise

if __name__ == '__main__':
    initialize_consul()
