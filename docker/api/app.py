import uuid
from flask import Flask, jsonify, request, abort
import docker
import time

app = Flask(__name__)
client = docker.from_env()
EMULATOR_IMAGE = "qemu-emulator"

# In-memory mapping of emulator sessions: id -> container
sessions = {}

@app.route('/emulators', methods=['POST'])
def create_emulator():
    session_id = str(uuid.uuid4())
    try:
        # Run container with random host ports
        container = client.containers.run(
            EMULATOR_IMAGE,
            detach=True,
            publish_all_ports=True,
            name=f"emu_{session_id}",
            privileged=True
        )
    except docker.errors.ImageNotFound:
        abort(500, description="Emulator image not found. Build qemu-emulator image first.")

    # wait until emulator binds ADB port
    for _ in range(30):
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        if ports.get('5555/tcp'):
            break
        time.sleep(1)

    sessions[session_id] = container
    return jsonify({ 'id': session_id, 'ports': ports }), 201

@app.route('/emulators/<session_id>', methods=['DELETE'])
def delete_emulator(session_id):
    container = sessions.get(session_id)
    if not container:
        abort(404)
    container.stop()
    container.remove()
    sessions.pop(session_id, None)
    return '', 204

@app.route('/emulators', methods=['GET'])
def list_emulators():
    data = {}
    for sid, container in sessions.items():
        container.reload()
        data[sid] = container.attrs['NetworkSettings']['Ports']
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)