from flask import Flask, jsonify
import os

app = Flask(__name__)

# Отримуємо адреси сервісів із змінних середовища
logging_services = os.environ.get("LOGGING_SERVICES", "logging1:50051,logging2:50052,logging3:50053").split(',')
messages_services = os.environ.get("MESSAGES_SERVICES", "messages:8882").split(',')

# Формуємо повні URL для logging-service
logging_services = [f"http://{addr}/logging" for addr in logging_services]
messages_services = [f"http://{addr}/messages" for addr in messages_services]

@app.route('/services/<service_name>', methods=['GET'])
def get_service_addresses(service_name):
    if service_name == "logging":
        return jsonify({"addresses": logging_services})
    elif service_name == "messages":
        return jsonify({"addresses": messages_services})
    else:
        return jsonify({"error": "Service not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8881)