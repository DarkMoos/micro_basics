import requests, uuid
from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, wait_fixed

app = Flask(__name__)
logging_service = 'http://localhost:8881/logging'
messages_service = 'http://localhost:8882/messages'

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def send_with_retry(url, data):
    response = requests.post(url, data=data)
    if response.status_code != 201:
        raise Exception('Logging service did not accept message.')
    return response

@app.route('/', methods=['POST', 'GET'])
def home():
    if request.method == 'POST':
        txt = request.form.get('txt')
        if not txt:
            return jsonify('No message'), 400
        id = str(uuid.uuid4())
        msg = {'id': id, 'txt': txt}
        try:
            send_with_retry(logging_service, msg)
            return jsonify(msg), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    elif request.method == 'GET':
        try:
            logging_response = requests.get(logging_service)
            messages_response = requests.get(messages_service)
            combined_response = [
                f'logging-service: {logging_response.text}',
                f'message-service: {messages_response.text}'
            ]
            return jsonify(combined_response), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(port=8880)
