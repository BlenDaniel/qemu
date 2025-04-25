import uuid
from flask import Flask, jsonify, request, abort
import docker
import time
import subprocess
import os

app = Flask(__name__)
client = docker.from_env()
EMULATOR_IMAGE = "qemu-emulator"

# In-memory mapping of emulator sessions: id -> container
sessions = {}

def check_adb_connectivity(ip, port=5555, timeout=5):
    """Check if ADB can connect to the emulator."""
    try:
        # Try to connect to the ADB server
        result = subprocess.run(
            f"adb connect {ip}:{port}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        # Check the output for success message
        if "connected to" in result.stdout.lower():
            return True, result.stdout.strip()
        else:
            return False, result.stdout.strip()
    except Exception as e:
        return False, str(e)

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

    # Wait longer for the emulator to fully initialize (up to 120 seconds)
    max_attempts = 120
    for attempt in range(max_attempts):
        try:
            container.reload()
            ports = container.attrs['NetworkSettings']['Ports']
            ip = container.attrs['NetworkSettings']['IPAddress']
            
            # ADB port is critical - wait until it's bound
            if ports.get('5555/tcp'):
                # Check if we can connect to the emulator
                if attempt % 10 == 0:  # Only check connectivity every 10 seconds
                    can_connect, message = check_adb_connectivity(ip)
                    if can_connect:
                        print(f"Successfully connected to emulator at {ip}:5555")
                        break
                    else:
                        print(f"ADB port is bound but connection failed: {message}")
            
            # If we're halfway through the timeout, restart the ADB server
            if attempt == max_attempts // 2:
                try:
                    subprocess.run("adb kill-server && adb start-server", shell=True, timeout=10)
                    print("Restarted ADB server to improve connectivity")
                except Exception as e:
                    print(f"Error restarting ADB server: {e}")
        except Exception as e:
            print(f"Error checking container state: {e}")
        
        # Provide status update every 10 seconds
        if attempt % 10 == 0:
            print(f"Waiting for container {session_id} to initialize... {attempt}s elapsed")
        
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
    
    # If we might have exited the loop because of timeout
    try:
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        ip = container.attrs['NetworkSettings']['IPAddress']
        
        if not ports.get('5555/tcp'):
            container.stop()
            container.remove()
            abort(500, description="Timeout waiting for emulator to bind ports.")
    except Exception as e:
        print(f"Error in final container check: {e}")
        abort(500, description=f"Error checking container: {e}")

    sessions[session_id] = container
    return jsonify({ 
        'id': session_id, 
        'ip': ip,
        'ports': ports,
        'status': 'running',
        'adb_connect': f"adb connect {ip}:{ports['5555/tcp'][0]['HostPort']}"
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
            ports = container.attrs['NetworkSettings']['Ports']
            ip = container.attrs['NetworkSettings']['IPAddress']
            
            # Get ADB connection status
            adb_status = "unknown"
            try:
                can_connect, message = check_adb_connectivity(ip)
                adb_status = "connected" if can_connect else "disconnected"
            except Exception as e:
                adb_status = f"error: {str(e)}"
            
            container_info = {
                'ports': ports,
                'status': container.status,
                'ip': ip,
                'adb_status': adb_status,
                'adb_connect': f"adb connect {ip}:{ports['5555/tcp'][0]['HostPort']}" if ports.get('5555/tcp') else None
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
        ports = container.attrs['NetworkSettings']['Ports']
        ip = container.attrs['NetworkSettings']['IPAddress']
        
        # Get ADB connection status
        adb_status = "unknown"
        try:
            can_connect, message = check_adb_connectivity(ip)
            adb_status = "connected" if can_connect else "disconnected"
        except Exception as e:
            adb_status = f"error: {str(e)}"
            
        container_info = {
            'id': session_id,
            'ports': ports,
            'status': container.status,
            'ip': ip,
            'adb_status': adb_status,
            'adb_connect': f"adb connect {ip}:{ports['5555/tcp'][0]['HostPort']}" if ports.get('5555/tcp') else None
        }
        return jsonify(container_info)
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'unknown'})

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    try:
        # Check Docker connection
        client.ping()
        return jsonify({'status': 'healthy', 'message': 'API is running and Docker connection is valid'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'message': f'Error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)