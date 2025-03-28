from flask import Flask, request, jsonify

app = Flask(__name__)
msg = {}

@app.route('/logging', methods=['POST', 'GET'])
def home():
    if request.method == 'POST':
        id, txt = request.form.get('id'), request.form.get('txt')
        if not (id and txt):
            return jsonify('No id or text'), 400

        if id in msg:
            print(f'Duplicate message detected: {id}')
            return jsonify('Duplicate detected'), 200

        msg[id] = txt
        print('Message:', txt)
        return jsonify('Message logged'), 201

    elif request.method == 'GET':
        return jsonify(list(msg.values()))

if __name__ == '__main__':
    app.run(port=8881)
