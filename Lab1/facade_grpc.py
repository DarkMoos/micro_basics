import grpc, uuid
from flask import Flask, request, jsonify
import logging_pb2, logging_pb2_grpc

app = Flask(__name__)
channel = grpc.insecure_channel('localhost:50051')
client = logging_pb2_grpc.LoggingServiceStub(channel)

@app.route('/', methods=['POST', 'GET'])
def home():
    if request.method == 'POST':
        txt = request.form.get('txt')
        if not txt:
            return jsonify('No message'), 400
        id = str(uuid.uuid4())
        response = client.LogMessage(logging_pb2.LogRequest(id=id, txt=txt))
        return jsonify({'id': id, 'status': response.status}), 200

    elif request.method == 'GET':
        response = client.GetMessages(logging_pb2.Empty())
        return jsonify(list(response.messages)), 200

if __name__ == '__main__':
    app.run(port=8880)
