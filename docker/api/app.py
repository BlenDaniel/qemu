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
        # Run container with explicit port bindings to ensure ADB is accessible
        container = client.containers.run(
            EMULATOR_IMAGE,
            detach=True,
            ports={
                '5037/tcp': None,  # ADB server
                '5554/tcp': None,  # Emulator console
                '5555/tcp': None,  # ADB connection
            },
            name=f"emu_{session_id}",
            privileged=True,
            extra_hosts={'host.docker.internal': 'host-gateway'}
        )
    except docker.errors.ImageNotFound:
        abort(500, description="Emulator image not found. Build qemu-emulator image first.")

    # Wait longer for the emulator to fully initialize (up to 60 seconds)
    for attempt in range(60):
        try:
            container.reload()
            ports = container.attrs['NetworkSettings']['Ports']
            # ADB port is critical - wait until it's bound
            if ports.get('5555/tcp'):
                print(f"Container {session_id} ready with ports: {ports}")
                break
        except Exception as e:
            print(f"Error checking container state: {e}")
        
        # Provide status update every 5 seconds
        if attempt % 5 == 0:
            print(f"Waiting for container {session_id} to bind ports... {attempt}s")
        
        # Check if container is still running
        try:
            container.reload()
            status = container.status
            if status != 'running':
                print(f"Container exited with status: {status}")
                abort(500, description=f"Emulator container exited unexpectedly with status: {status}")
        except Exception as e:
            print(f"Error checking container status: {e}")
        
        time.sleep(1)
    
    # If we exit the loop because of timeout
    if not ports.get('5555/tcp'):
        container.stop()
        container.remove()
        abort(500, description="Timeout waiting for emulator to bind ports.")

    sessions[session_id] = container
    return jsonify({ 
        'id': session_id, 
        'ports': ports,
        'status': 'running',
        'ip': container.attrs['NetworkSettings']['IPAddress']
    }), 201

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
        try:
            container.reload()
            container_info = {
                'ports': container.attrs['NetworkSettings']['Ports'],
                'status': container.status,
                'ip': container.attrs['NetworkSettings']['IPAddress']
            }
            data[sid] = container_info
        except Exception as e:
            data[sid] = {'error': str(e), 'status': 'unknown'}
    return jsonify(data)

@app.route('/emulators/<session_id>', methods=['GET'])
def get_emulator(session_id):
    container = sessions.get(session_id)
    if not container:
        abort(404)
    
    try:
        container.reload()
        container_info = {
            'id': session_id,
            'ports': container.attrs['NetworkSettings']['Ports'],
            'status': container.status,
            'ip': container.attrs['NetworkSettings']['IPAddress']
        }
        return jsonify(container_info)
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'unknown'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)