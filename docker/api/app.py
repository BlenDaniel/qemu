import uuid
import os
import socket
from flask import Flask, jsonify, request, abort
import docker
import time
import subprocess
from typing import Dict, Any, Optional

app = Flask(__name__)
client = docker.from_env()
EMULATOR_IMAGE = "qemu-emulator"

# In-memory mapping of emulator sessions: id -> container
sessions = {}

# Get host machine IP for display in connection instructions
def get_host_ip() -> str:
    try:
        # This gets the IP that can connect to the internet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        host_ip = s.getsockname()[0]
        s.close()
        return host_ip
    except Exception:
        return "localhost"  # Fallback

# Helper function to check if a port is available
def is_port_available(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result != 0  # If not zero, port is available

# Find an available port in a range
def find_available_port(start_port: int, end_port: int) -> Optional[int]:
    for port in range(start_port, end_port + 1):
        if is_port_available(port):
            return port
    return None

@app.route('/emulators', methods=['POST'])
def create_emulator():
    session_id = str(uuid.uuid4())
    
    # Find available ports for each service
    adb_server_port = find_available_port(5037, 5047)
    console_port = find_available_port(5554, 5564)
    adb_port = find_available_port(5555, 5565)
    
    if not all([adb_server_port, console_port, adb_port]):
        abort(500, description="Could not find available ports")
    
    # Create port bindings
    port_bindings = {
        '5037/tcp': ('0.0.0.0', adb_server_port),  # ADB server
        '5554/tcp': ('0.0.0.0', console_port),    # Emulator console
        '5555/tcp': ('0.0.0.0', adb_port),       # ADB connection
    }
    
    try:
        # Run container with explicit port bindings to ensure ADB is accessible
        container = client.containers.run(
            EMULATOR_IMAGE,
            detach=True,
            ports=port_bindings,
            name=f"emu_{session_id}",
            privileged=True,
            extra_hosts={'host.docker.internal': 'host-gateway'}
        )
    except docker.errors.ImageNotFound:
        abort(500, description="Emulator image not found. Build qemu-emulator image first.")
    except Exception as e:
        abort(500, description=f"Error starting container: {str(e)}")

    # Wait longer for the emulator to fully initialize (up to 120 seconds)
    print(f"Starting container {session_id} with ports: ADB={adb_port}, Console={console_port}")
    
    for attempt in range(120):
        try:
            container.reload()
            ports = container.attrs['NetworkSettings']['Ports']
            # ADB port is critical - wait until it's bound
            if ports.get('5555/tcp'):
                # Verify the port mapping
                mapped_port = ports['5555/tcp'][0]['HostPort']
                if mapped_port == str(adb_port):
                    print(f"Container {session_id} ready with ADB port: {mapped_port}")
                    break
                else:
                    print(f"Warning: Port mismatch. Expected {adb_port}, got {mapped_port}")
        except Exception as e:
            print(f"Error checking container state: {e}")
        
        # Provide status update every 10 seconds
        if attempt % 10 == 0:
            print(f"Waiting for container {session_id}... {attempt}s")
        
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
    
    # Wait additional time for the ADB connection to become available
    print(f"Waiting for ADB service to be available at port {adb_port}...")
    time.sleep(15)  # Give ADB time to start up in TCP mode
    
    # Try to connect to the ADB instance from the API server
    try:
        subprocess.run(["adb", "connect", f"localhost:{adb_port}"], 
                     check=False, capture_output=True, timeout=5)
        print(f"Test ADB connection to localhost:{adb_port} completed")
    except Exception as e:
        print(f"Error testing ADB connection: {e}")
    
    # Store the session in our registry
    sessions[session_id] = container
    
    # Get host information for connection instructions
    host_ip = get_host_ip()
    
    # Build the response with detailed connection information
    return jsonify({ 
        'id': session_id, 
        'ports': {
            'adb_server': adb_server_port,
            'console': console_port,
            'adb': adb_port
        },
        'status': 'running',
        'ip': container.attrs['NetworkSettings']['IPAddress'],
        'connection_command': f"adb connect {host_ip}:{adb_port}",
        'raw_ports': ports
    }), 201

@app.route('/emulators/<session_id>', methods=['DELETE'])
def delete_emulator(session_id):
    container = sessions.get(session_id)
    if not container:
        abort(404)
        
    try:
        # Try to disconnect ADB first
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        if ports and '5555/tcp' in ports:
            adb_port = ports['5555/tcp'][0]['HostPort']
            try:
                subprocess.run(["adb", "disconnect", f"localhost:{adb_port}"], 
                             check=False, capture_output=True, timeout=5)
            except Exception:
                pass  # Ignore ADB disconnect errors
        
        # Now stop and remove container
        container.stop()
        container.remove()
        sessions.pop(session_id, None)
        return '', 204
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/emulators', methods=['GET'])
def list_emulators():
    data = {}
    host_ip = get_host_ip()
    
    for sid, container in sessions.items():
        try:
            container.reload()
            ports = container.attrs['NetworkSettings']['Ports']
            
            # Get the ADB port
            adb_port = ports.get('5555/tcp', [{}])[0].get('HostPort', 'unknown') if ports else 'unknown'
            
            container_info = {
                'ports': ports,
                'status': container.status,
                'ip': container.attrs['NetworkSettings']['IPAddress'],
                'connection_command': f"adb connect {host_ip}:{adb_port}" if adb_port != 'unknown' else 'unknown'
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
    
    host_ip = get_host_ip()
    
    try:
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        
        # Get the ADB port
        adb_port = ports.get('5555/tcp', [{}])[0].get('HostPort', 'unknown') if ports else 'unknown'
        
        container_info = {
            'id': session_id,
            'ports': ports,
            'status': container.status,
            'ip': container.attrs['NetworkSettings']['IPAddress'],
            'connection_command': f"adb connect {host_ip}:{adb_port}" if adb_port != 'unknown' else 'unknown'
        }
        return jsonify(container_info)
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'unknown'})

@app.route('/emulators/<session_id>/connect', methods=['POST'])
def connect_to_emulator(session_id):
    """Helper endpoint to connect to an emulator via ADB"""
    container = sessions.get(session_id)
    if not container:
        abort(404)
    
    try:
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        
        if not ports or '5555/tcp' not in ports:
            return jsonify({'error': 'ADB port not mapped'}), 400
        
        adb_port = ports['5555/tcp'][0]['HostPort']
        host_ip = get_host_ip()
        
        # Try to connect via ADB
        result = subprocess.run(
            ["adb", "connect", f"{host_ip}:{adb_port}"], 
            capture_output=True, 
            text=True,
            check=False
        )
        
        return jsonify({
            'success': 'connected' in result.stdout,
            'command': f"adb connect {host_ip}:{adb_port}",
            'output': result.stdout,
            'error': result.stderr if result.returncode != 0 else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)