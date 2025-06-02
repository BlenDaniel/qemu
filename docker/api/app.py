# Unified Android Emulator Management API and Web Interface
import uuid
import platform
import time
import random
import subprocess
import string
import shlex
import logging
import os
import threading
import socket
from flask import Flask, jsonify, request, abort, render_template

# External dependencies
import docker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Make Docker client initialization lazy for testing
client = None

def get_docker_client():
    global client
    if client is None:
        try:
            # Try different connection methods
            # First try the default method
            client = docker.from_env()
            # Test the connection
            client.ping()
            logger.info("Docker client connected successfully")
        except Exception as e:
            logger.warning(f"Default Docker connection failed: {e}")
            try:
                # Try explicit Unix socket connection
                client = docker.DockerClient(base_url='unix://var/run/docker.sock')
                client.ping()
                logger.info("Docker client connected via Unix socket")
            except Exception as e2:
                logger.warning(f"Unix socket connection failed: {e2}")
                try:
                    # Try TCP connection
                    client = docker.DockerClient(base_url='tcp://localhost:2376')
                    client.ping()
                    logger.info("Docker client connected via TCP")
                except Exception as e3:
                    logger.error(f"All Docker connection methods failed: {e3}")
                    # Set client to None so we can provide better error messages
                    client = None
    return client

# Emulator image configurations
EMULATOR_IMAGES = {
    "11": "qemu-emulator",           # Android 11 image
    "14": "qemu-emulator-android14"  # Android 14 image
}

# In-memory mapping of emulator sessions: id -> container
sessions = {}

def generate_device_id():
    """Generate a unique device ID for the emulator"""
    letters_and_digits = string.ascii_lowercase + string.digits
    device_id = ''.join(random.choice(letters_and_digits) for _ in range(8))
    return device_id

def set_adb_environment(adb_server_port=None, device_port=None):
    """Set environment variables for ADB operations"""
    if adb_server_port:
        os.environ['ANDROID_ADB_SERVER_PORT'] = str(adb_server_port)
        logger.info(f"Set ADB server port to: {adb_server_port}")
    
    if device_port:
        os.environ['ANDROID_SERIAL'] = f"localhost:{device_port}"
        logger.info(f"Set default device to: localhost:{device_port}")

def run_adb_command(command, args=None, adb_server_port=None):
    """Run an ADB command and return the output"""
    if adb_server_port:
        set_adb_environment(adb_server_port=adb_server_port)
    
    full_command = ["adb"]
    if args:
        full_command.extend(args)
    
    try:
        logger.info(f"Running ADB command: {' '.join(full_command)}")
        result = subprocess.run(full_command, capture_output=True, text=True, check=True)
        return {"success": True, "output": result.stdout}
    except subprocess.CalledProcessError as e:
        logger.error(f"ADB command failed: {e.stderr}")
        return {"success": False, "error": e.stderr}

def kill_all_adb_processes():
    """Attempt to kill every stray adb process that might still be running."""
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "adb"], capture_output=True)
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning(f"Error while killing stray adb processes: {exc}")

def wait_for_device(adb_server_port: str, device_port: str, timeout: int = 60, interval: int = 2):
    """Poll `adb devices` until the given localhost:<port> appears or timeout."""
    target_serial = f"localhost:{device_port}"
    deadline = time.time() + timeout

    while time.time() < deadline:
        result = run_adb_command("devices", ["devices"], adb_server_port=adb_server_port)
        if result.get("success"):
            lines = result["output"].splitlines()[1:]  # skip header
            for line in lines:
                parts = shlex.split(line)
                if not parts:
                    continue
                serial = parts[0]
                status = parts[1] if len(parts) > 1 else "unknown"
                if serial == target_serial:
                    return status
        time.sleep(interval)
    return "absent"

# ============================================================================
# WEB INTERFACE ROUTES
# ============================================================================

@app.route('/health')
def health_check():
    """Health check endpoint"""
    docker_client = get_docker_client()
    if docker_client is None:
        return jsonify({
            "status": "unhealthy",
            "docker": "disconnected",
            "message": "Cannot connect to Docker daemon"
        }), 503
    
    try:
        docker_client.ping()
        return jsonify({
            "status": "healthy", 
            "docker": "connected",
            "message": "API and Docker are working properly"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "docker": "error", 
            "message": f"Docker ping failed: {str(e)}"
        }), 503

@app.route('/')
def index():
    """Render the main dashboard"""
    return render_template('index.html')

# ============================================================================
# EMULATOR MANAGEMENT API ROUTES
# ============================================================================

@app.route('/api/emulators', methods=['POST'])
def create_emulator():
    """Create a new emulator"""
    session_id = str(uuid.uuid4())
    device_id = generate_device_id()
    
    # Check Docker connection first
    docker_client = get_docker_client()
    if docker_client is None:
        abort(500, description="Docker daemon is not accessible. Please check if Docker is running and the API container has proper permissions.")
    
    # Get request data
    data = request.get_json(silent=True) or {}
    
    # Get Android version (default to 11)
    android_version = str(data.get('android_version', '11'))
    if android_version not in EMULATOR_IMAGES:
        android_version = '11'  # fallback to Android 11
    
    emulator_image = EMULATOR_IMAGES[android_version]
    
    # Generate random host ports for all services
    default_console_port = random.randint(5000, 9999)
    default_adb_port = random.randint(5000, 9999)
    internal_adb_server_port = random.randint(5000, 9999)
    vnc_port = random.randint(5900, 6000)  # VNC port range
    
    # Get custom port mappings if provided, or use defaults
    console_port = data.get('console_port', default_console_port)
    adb_port = data.get('adb_port', default_adb_port)
    
    # Check if external ADB server is explicitly requested
    map_external_adb_server = data.get('map_adb_server', True)  # Default to True now
    external_adb_server_port = data.get('adb_server_port')
    
    # Prepare port bindings for required ports
    port_bindings = {
        '5554/tcp': console_port,
        '5555/tcp': adb_port,
        '5037/tcp': internal_adb_server_port,
        '5900/tcp': vnc_port  # VNC server port
    }
    
    # If external ADB server was requested, override with specified port
    if map_external_adb_server and external_adb_server_port:
        port_bindings['5037/tcp'] = external_adb_server_port
    
    # Prepare environment variables
    environment = {
        'ANDROID_EMULATOR_WAIT_TIME': '120',
        'ANDROID_EMULATED_DEVICE': android_version,
        'ANDROID_EXTRA_OPTS': f'-gpu swiftshader_indirect -no-snapshot -noaudio -no-boot-anim -no-snapshot-save -avd {device_id}',
        'DEVICE_PORT': str(console_port),
        'DEVICE_ID': device_id,
        'ENABLE_VNC': 'true',  # Enable VNC server
        'VNC_PORT': '5900'     # Internal VNC port
    }
    
    try:
        # Run container with specified port bindings
        container = docker_client.containers.run(
            emulator_image,
            detach=True,
            privileged=True,
            environment=environment,
            name=f"emu_{device_id}_{session_id[:8]}",
            ports=port_bindings
        )
    except docker.errors.ImageNotFound:
        abort(500, description=f"Emulator image {emulator_image} not found. Build the image first.")
    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        abort(500, description=f"Docker API error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to create emulator: {e}")
        abort(500, description=f"Failed to create emulator: {str(e)}")

    # Wait until emulator binds ADB port
    for _ in range(60):
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        if ports and ports.get('5555/tcp'):
            break
        time.sleep(1)
    else:
        container.stop()
        container.remove()
        abort(500, description="Emulator failed to start properly")

    # Get the actual port mappings
    mapped_ports = {
        'console': ports.get('5554/tcp', [{}])[0].get('HostPort', 'unknown'),
        'adb': ports.get('5555/tcp', [{}])[0].get('HostPort', 'unknown'),
        'adb_server': ports.get('5037/tcp', [{}])[0].get('HostPort', 'unknown'),
        'vnc': ports.get('5900/tcp', [{}])[0].get('HostPort', 'unknown')
    }
    
    # Generate ADB commands for connecting to this emulator
    adb_commands = {
        'connect': f"adb connect localhost:{mapped_ports['adb']}",
        'server': f"adb -P {mapped_ports['adb_server']} devices",
        'set_server_unix': f"export ANDROID_ADB_SERVER_PORT={mapped_ports['adb_server']}",
        'set_server_windows': f"$env:ANDROID_ADB_SERVER_PORT = \"{mapped_ports['adb_server']}\"",
        'kill_and_restart_server': f"adb kill-server && adb -P {mapped_ports['adb_server']} start-server"
    }
    
    sessions[session_id] = {
        'container': container,
        'device_port': mapped_ports['console'],
        'ports': mapped_ports,
        'device_id': device_id,
        'android_version': android_version,
        'adb_commands': adb_commands,
        'has_external_adb_server': map_external_adb_server,
        'vnc_port': mapped_ports['vnc']  # Store VNC port for GUI access
    }
    
    # Setup ADB connection automatically
    adb_server_port = mapped_ports['adb_server']
    adb_device_port = mapped_ports['adb']
    
    # Set environment for current process
    set_adb_environment(adb_server_port=adb_server_port)
    
    # Kill existing ADB server and start fresh
    run_adb_command("kill-server", ["kill-server"], adb_server_port=adb_server_port)
    kill_all_adb_processes()
    
    # Start new ADB server
    run_adb_command("start-server", ["-P", str(adb_server_port), "start-server"], adb_server_port=adb_server_port)
    
    # Connect to the device
    connect_result = run_adb_command(
        "connect",
        ["connect", f"localhost:{adb_device_port}"],
        adb_server_port=adb_server_port,
    )
    
    # Wait for device to appear
    final_status = wait_for_device(adb_server_port, adb_device_port)
    
    # Get current devices list
    devices_result = run_adb_command("devices", ["devices"], adb_server_port=adb_server_port)
    
    # Log creation info
    logger.info(f"Created Android {android_version} emulator {device_id}")
    logger.info(f"Console: telnet localhost {mapped_ports['console']}")
    logger.info(f"ADB Server Port: {mapped_ports['adb_server']}")
    
    response_data = {
        'id': session_id,
        'device_id': device_id,
        'android_version': android_version,
        'device_port': mapped_ports['console'],
        'ports': mapped_ports,
        'adb_commands': adb_commands,
        'has_external_adb_server': map_external_adb_server,
        'adb_setup': {
            'kill_server': True,
            'server_port': adb_server_port,
            'connect_output': connect_result,
            'devices_output': devices_result,
            'final_device_status': final_status,
        }
    }
    
    return jsonify(response_data), 201

@app.route('/api/emulators/<session_id>', methods=['DELETE'])
def delete_emulator(session_id):
    """Delete an emulator"""
    session = sessions.get(session_id)
    if not session:
        abort(404)
    
    # Disconnect ADB from this emulator before removing it
    try:
        adb_host_port = session.get('ports', {}).get('adb')
        if adb_host_port and adb_host_port != 'unknown':
            subprocess.run(['adb', 'disconnect', f'localhost:{adb_host_port}'], 
                          check=False, 
                          capture_output=True, 
                          text=True)
    except Exception as e:
        logger.warning(f"Failed to disconnect ADB from emulator: {str(e)}")
    
    container = session['container']
    container.stop()
    container.remove()
    sessions.pop(session_id, None)
    
    logger.info(f"Deleted emulator {session.get('device_id', 'unknown')}")
    return '', 204

@app.route('/api/emulators', methods=['GET'])
def list_emulators():
    """List all emulators"""
    data = {}
    for sid, session in sessions.items():
        container = session['container']
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        
        mapped_ports = {
            'console': ports.get('5554/tcp', [{}])[0].get('HostPort', 'unknown'),
            'adb': ports.get('5555/tcp', [{}])[0].get('HostPort', 'unknown'),
            'adb_server': ports.get('5037/tcp', [{}])[0].get('HostPort', 'unknown'),
            'vnc': ports.get('5900/tcp', [{}])[0].get('HostPort', 'unknown')
        }
        
        # Generate or retrieve ADB commands
        if 'adb_commands' in session:
            adb_commands = session['adb_commands']
        else:
            adb_commands = {
                'connect': f"adb connect localhost:{mapped_ports['adb']}",
                'server': f"adb -P {mapped_ports['adb_server']} devices",
                'set_server_unix': f"export ANDROID_ADB_SERVER_PORT={mapped_ports['adb_server']}",
                'set_server_windows': f"set ANDROID_ADB_SERVER_PORT={mapped_ports['adb_server']}",
                'kill_and_restart_server': f"adb kill-server && adb -P {mapped_ports['adb_server']} start-server"
            }
            session['adb_commands'] = adb_commands
        
        device_id = session.get('device_id', 'unknown')
        android_version = session.get('android_version', '11')
        
        data[sid] = {
            'device_id': device_id,
            'android_version': android_version,
            'device_port': session['device_port'],
            'ports': mapped_ports,
            'status': container.status,
            'adb_commands': adb_commands,
            'has_external_adb_server': session.get('has_external_adb_server', False)
        }
    
    return jsonify(data)

# ============================================================================
# ADB MANAGEMENT API ROUTES
# ============================================================================

@app.route('/api/adb/connect', methods=['POST'])
def connect_to_emulator():
    """Connect to an emulator via ADB"""
    data = request.json
    port = data.get('adb_port')
    adb_server_port = data.get('adb_server_port')
    
    if not port:
        return jsonify({"error": "ADB port is required"}), 400
    
    if adb_server_port:
        set_adb_environment(adb_server_port=adb_server_port)
    
    result = run_adb_command("connect", ["connect", f"localhost:{port}"])
    
    if result.get('success'):
        set_adb_environment(device_port=port)
    
    return jsonify(result)

@app.route('/api/adb/disconnect', methods=['POST'])
def disconnect_device():
    """Disconnect a device from ADB"""
    data = request.json
    device = data.get('device')
    adb_server_port = data.get('adb_server_port')
    
    if not device:
        return jsonify({"error": "Device ID is required"}), 400
    
    if adb_server_port:
        set_adb_environment(adb_server_port=adb_server_port)
    
    result = run_adb_command("disconnect", ["disconnect", device])
    return jsonify(result)

@app.route('/api/adb/install', methods=['POST'])
def install_apk():
    """Install an APK on a connected device"""
    data = request.json
    apk_path = data.get('apk_path')
    device = data.get('device')
    adb_server_port = data.get('adb_server_port')
    
    if not apk_path:
        return jsonify({"error": "APK path is required"}), 400
    
    if adb_server_port:
        set_adb_environment(adb_server_port=adb_server_port)
    
    args = ["install"]
    if device:
        args.extend(["-s", device])
    args.append(apk_path)
    
    result = run_adb_command("install", args)
    return jsonify(result)

@app.route('/api/adb/devices', methods=['GET'])
def list_devices():
    """List connected ADB devices"""
    adb_server_port = request.args.get('port')
    
    if adb_server_port:
        set_adb_environment(adb_server_port=adb_server_port)
    
    result = run_adb_command("devices", ["devices"])
    return jsonify(result)

@app.route('/api/adb/kill-server', methods=['POST'])
def kill_adb_server():
    """Kill the ADB server"""
    adb_server_port = request.json.get('port') if request.is_json else None
    
    if adb_server_port:
        set_adb_environment(adb_server_port=adb_server_port)
    
    result = run_adb_command("kill-server", ["kill-server"])
    return jsonify(result)

@app.route('/api/adb/start-server', methods=['POST'])
def start_adb_server():
    """Start the ADB server"""
    data = request.json or {}
    port = data.get('port', '5037')
    
    set_adb_environment(adb_server_port=port)
    
    args = ["start-server"]
    if port != '5037':
        args = ["-P", port, "start-server"]
    
    result = run_adb_command("start-server", args)
    return jsonify(result)

# ============================================================================
# LEGACY ENDPOINTS (for backwards compatibility)
# ============================================================================

@app.route('/emulators', methods=['POST'])
def create_emulator_legacy():
    """Legacy endpoint for creating emulators"""
    return create_emulator()

@app.route('/emulators/<session_id>', methods=['DELETE'])
def delete_emulator_legacy(session_id):
    """Legacy endpoint for deleting emulators"""
    return delete_emulator(session_id)

@app.route('/emulators', methods=['GET'])
def list_emulators_legacy():
    """Legacy endpoint for listing emulators"""
    return list_emulators()

@app.route('/adb', methods=['GET'])
def adb_status():
    """Legacy ADB status endpoint"""
    port = request.args.get('adb')
    if not port:
        return jsonify({'error': 'adb port is required'}), 400
    try:
        port_int = int(port)
    except ValueError:
        return jsonify({'error': 'invalid port value'}), 400
    
    env_var = 'ANDROID_ADB_SERVER_PORT'
    os.environ[env_var] = str(port_int)
    
    if platform.system() == 'Windows':
        subprocess.run(['powershell', '-Command', f'$env:{env_var}={port_int}'], capture_output=True)
    
    subprocess.run(['adb', 'kill-server'], capture_output=True)
    subprocess.run(['adb', '-P', str(port_int), 'start-server'], capture_output=True)
    devices_res = subprocess.run(['adb', '-P', str(port_int), 'devices'], capture_output=True, text=True)
    return jsonify({'adb_port': port_int, 'devices': devices_res.stdout.splitlines()}), 200

@app.route('/vnc/<emulator_id>')
def vnc_viewer(emulator_id):
    """Serve VNC viewer for emulator screen"""
    if emulator_id not in sessions:
        return "Emulator not found", 404
    
    session = sessions[emulator_id]
    vnc_port = session.get('vnc_port')
    
    if not vnc_port:
        return "VNC not available for this emulator", 404
    
    # Return noVNC viewer HTML
    return render_template('vnc_viewer.html', 
                         emulator_id=emulator_id,
                         vnc_port=vnc_port,
                         device_id=session['device_id'])

@app.route('/api/emulators/<emulator_id>/vnc')
def vnc_proxy(emulator_id):
    """HTTP endpoint to get VNC connection info"""
    if emulator_id not in sessions:
        return jsonify({"error": "Emulator not found"}), 404
    
    session = sessions[emulator_id]
    vnc_port = session.get('vnc_port')
    
    if not vnc_port or vnc_port == 'unknown':
        return jsonify({"error": "VNC not available for this emulator"}), 404
    
    return jsonify({
        "success": True,
        "vnc_port": vnc_port,
        "vnc_host": "localhost",
        "connection_info": {
            "direct_vnc": f"vnc://localhost:{vnc_port}",
            "instructions": "VNC server is running but WebSocket connection may require additional setup. Use screenshot feature as alternative."
        }
    })

@app.route('/api/emulators/<emulator_id>/live_view')
def live_view(emulator_id):
    """Provide a live view page with periodic screenshots"""
    if emulator_id not in sessions:
        return "Emulator not found", 404
    
    session = sessions[emulator_id]
    device_id = session.get('device_id', 'unknown')
    
    return render_template('live_view.html', 
                         emulator_id=emulator_id,
                         device_id=device_id)

@app.route('/api/emulators/<emulator_id>/screenshot')
def get_screenshot(emulator_id):
    """Get screenshot from emulator"""
    if emulator_id not in sessions:
        return jsonify({"error": "Emulator not found"}), 404
    
    session = sessions[emulator_id]
    adb_port = session['ports']['adb']
    adb_server_port = session['ports']['adb_server']
    
    try:
        # Take screenshot using ADB with proper command structure
        # Use exec-out to get binary data directly
        cmd = [
            "adb", "-P", str(adb_server_port), 
            "-s", f"localhost:{adb_port}", 
            "exec-out", "screencap", "-p"
        ]
        
        logger.info(f"Running screenshot command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, check=True)
        
        if result.returncode == 0 and result.stdout:
            # Return screenshot as base64
            import base64
            screenshot_b64 = base64.b64encode(result.stdout).decode()
            return jsonify({"success": True, "screenshot": f"data:image/png;base64,{screenshot_b64}"})
        else:
            return jsonify({"success": False, "error": "Failed to capture screenshot - no data returned"})
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Screenshot command failed: {e.stderr}")
        return jsonify({"success": False, "error": f"ADB command failed: {e.stderr.decode() if e.stderr else 'Unknown error'}"})
    except Exception as e:
        logger.error(f"Screenshot error: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)