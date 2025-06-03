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
from websockify import WebSocketProxy

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

# Predefined container configurations for docker-compose containers
PREDEFINED_CONTAINERS = {
    "emulator": {
        "container_name_pattern": "qemu-main-emulator",
        "android_version": "11",
        "device_id": "android11_main",
        "ports": {
            "console": "5554",
            "adb": "5555", 
            "adb_server": "5037",
            "vnc": "5901"
        }
    },
    "emulator14": {
        "container_name_pattern": "qemu-main-emulator14", 
        "android_version": "14",
        "device_id": "android14_main",
        "ports": {
            "console": "6654",
            "adb": "6655",
            "adb_server": "6037", 
            "vnc": "5902"
        }
    }
}

# In-memory mapping of emulator sessions: id -> container
sessions = {}

# Global WebSocket proxy servers
vnc_proxies = {}

def discover_existing_containers():
    """Discover and register existing emulator containers on startup"""
    docker_client = get_docker_client()
    if not docker_client:
        logger.warning("Cannot discover containers - Docker client not available")
        return
    
    try:
        # Get all running containers
        containers = docker_client.containers.list()
        
        for container in containers:
            container_name = container.name
            logger.info(f"Checking container: {container_name}")
            
            # Check if this is one of our predefined emulator containers
            for service_name, config in PREDEFINED_CONTAINERS.items():
                if config["container_name_pattern"] in container_name:
                    # Generate session ID for this container
                    session_id = f"existing_{service_name}_{config['device_id']}"
                    
                    # Register container in sessions
                    sessions[session_id] = {
                        'container': container,
                        'device_port': config['ports']['console'],
                        'ports': config['ports'],
                        'device_id': config['device_id'],
                        'android_version': config['android_version'],
                        'has_external_adb_server': True,
                        'vnc_port': config['ports']['vnc'],
                        'is_predefined': True
                    }
                    
                    logger.info(f"Registered existing container {container_name} as session {session_id}")
                    
                    # Try to set up ADB connection
                    setup_adb_for_existing_container(session_id, config)
                    break
                    
    except Exception as e:
        logger.error(f"Error discovering existing containers: {e}")

def setup_adb_for_existing_container(session_id, config):
    """Set up ADB connection for an existing container"""
    try:
        adb_server_port = config['ports']['adb_server']
        adb_device_port = config['ports']['adb']
        
        logger.info(f"Setting up ADB for {session_id} - server port: {adb_server_port}, device port: {adb_device_port}")
        
        # Use robust ADB server restart
        if not robust_adb_server_restart(adb_server_port):
            logger.error(f"Failed to restart ADB server for {session_id}")
            return False
        
        # Use robust device detection
        device_status = detect_device_with_retry(adb_server_port, adb_device_port, max_retries=5, retry_delay=2)
        
        if device_status in ["device", "offline"]:
            logger.info(f"Successfully connected to device for {session_id} with status: {device_status}")
            return True
        else:
            logger.warning(f"Failed to connect to device for {session_id}. Status: {device_status}")
            return False
        
    except Exception as e:
        logger.error(f"Failed to setup ADB for {session_id}: {e}")
        return False

# Discover existing containers on module load
discover_existing_containers()

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
        
        # Also set for current shell session based on platform
        try:
            if platform.system() == "Windows":
                # Set PowerShell environment variable
                ps_cmd = f'$env:ANDROID_ADB_SERVER_PORT = "{adb_server_port}"'
                subprocess.run(['powershell', '-Command', ps_cmd], capture_output=True, timeout=5)
                logger.info(f"Set Windows PowerShell ADB server port to: {adb_server_port}")
            else:
                # Set bash environment variable
                bash_cmd = f'export ANDROID_ADB_SERVER_PORT={adb_server_port}'
                subprocess.run(['bash', '-c', bash_cmd], capture_output=True, timeout=5)
                logger.info(f"Set Unix shell ADB server port to: {adb_server_port}")
        except Exception as e:
            logger.warning(f"Failed to set shell environment variable: {e}")
    
    if device_port:
        os.environ['ANDROID_SERIAL'] = f"localhost:{device_port}"
        logger.info(f"Set default device to: localhost:{device_port}")

def run_adb_command(command, args=None, adb_server_port=None, timeout=30):
    """Run an ADB command and return the output"""
    if adb_server_port:
        set_adb_environment(adb_server_port=adb_server_port)
    
    full_command = ["adb"]
    if args:
        full_command.extend(args)
    
    try:
        logger.info(f"Running ADB command: {' '.join(full_command)}")
        result = subprocess.run(full_command, capture_output=True, text=True, check=True, timeout=timeout)
        return {"success": True, "output": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as e:
        logger.error(f"ADB command failed: {e.stderr}")
        return {"success": False, "error": e.stderr, "stdout": e.stdout if e.stdout else ""}
    except subprocess.TimeoutExpired as e:
        logger.error(f"ADB command timed out after {timeout}s")
        return {"success": False, "error": f"Command timed out after {timeout}s"}

def kill_all_adb_processes():
    """Attempt to kill every stray adb process that might still be running."""
    try:
        logger.info("Killing all ADB processes...")
        if platform.system() == "Windows":
            # Kill ADB processes on Windows
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], capture_output=True, timeout=10)
            logger.info("Killed Windows ADB processes")
        else:
            # Kill ADB processes on Unix-like systems
            subprocess.run(["pkill", "-f", "adb"], capture_output=True, timeout=10)
            logger.info("Killed Unix ADB processes")
        
        # Also try generic approach
        subprocess.run(["adb", "kill-server"], capture_output=True, timeout=10)
        logger.info("Executed adb kill-server")
        
    except FileNotFoundError:
        logger.warning("ADB binary not found in PATH")
    except Exception as exc:
        logger.warning(f"Error while killing stray adb processes: {exc}")

def robust_adb_server_restart(adb_server_port):
    """Robustly restart ADB server with proper cleanup"""
    try:
        logger.info(f"Performing robust ADB server restart on port {adb_server_port}")
        
        # Step 1: Kill all existing ADB processes
        kill_all_adb_processes()
        
        # Step 2: Wait for processes to die
        time.sleep(2)
        
        # Step 3: Set environment
        set_adb_environment(adb_server_port=adb_server_port)
        
        # Step 4: Start new ADB server
        start_result = run_adb_command("start-server", ["-P", str(adb_server_port), "start-server"], adb_server_port=adb_server_port, timeout=15)
        
        if start_result.get("success"):
            logger.info(f"ADB server started successfully on port {adb_server_port}")
            # Wait for server to be ready
            time.sleep(3)
            return True
        else:
            logger.error(f"Failed to start ADB server: {start_result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"Error during ADB server restart: {e}")
        return False

def detect_device_with_retry(adb_server_port, device_port, max_retries=10, retry_delay=3):
    """Detect device with multiple retries and better error handling"""
    target_serial = f"localhost:{device_port}"
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Device detection attempt {attempt + 1}/{max_retries} for {target_serial}")
            
            # First, try to connect to the device
            connect_result = run_adb_command(
                "connect", 
                ["-P", str(adb_server_port), "connect", target_serial], 
                adb_server_port=adb_server_port,
                timeout=15
            )
            
            logger.info(f"Connect attempt result: {connect_result}")
            
            # Wait for connection to stabilize
            time.sleep(2)
            
            # Now check if device appears in devices list
            devices_result = run_adb_command(
                "devices", 
                ["-P", str(adb_server_port), "devices"], 
                adb_server_port=adb_server_port,
                timeout=10
            )
            
            if devices_result.get("success"):
                logger.info(f"Devices output: {devices_result['output']}")
                
                # Parse devices output
                lines = devices_result["output"].strip().split('\n')
                if len(lines) > 1:  # Skip header
                    for line in lines[1:]:
                        if line.strip():
                            parts = line.strip().split('\t')
                            if len(parts) >= 1:
                                serial = parts[0]
                                status = parts[1] if len(parts) > 1 else "unknown"
                                
                                if serial == target_serial:
                                    logger.info(f"Found device {target_serial} with status: {status}")
                                    return status
                
                logger.warning(f"Device {target_serial} not found in devices list")
            else:
                logger.warning(f"Failed to get devices list: {devices_result.get('error')}")
            
            # If we didn't find the device, wait and retry
            if attempt < max_retries - 1:
                logger.info(f"Retrying device detection in {retry_delay} seconds...")
                time.sleep(retry_delay)
            
        except Exception as e:
            logger.error(f"Error during device detection attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    logger.error(f"Failed to detect device {target_serial} after {max_retries} attempts")
    return "not_found"

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

def start_vnc_proxy(emulator_id, vnc_port, proxy_port):
    """Start a WebSocket proxy for VNC connections"""
    try:
        # Kill any existing proxy on this port
        stop_vnc_proxy(emulator_id)
        
        print(f"Starting VNC proxy for {emulator_id}: VNC port {vnc_port} -> WebSocket port {proxy_port}")
        
        # Start websockify proxy in a separate thread
        def run_proxy():
            try:
                proxy = WebSocketProxy(
                    listen_host='0.0.0.0',
                    listen_port=proxy_port,
                    target_host='localhost',
                    target_port=vnc_port,
                    verbose=True
                )
                vnc_proxies[emulator_id] = proxy
                proxy.start_server()
            except Exception as e:
                print(f"VNC proxy error for {emulator_id}: {e}")
                
        proxy_thread = threading.Thread(target=run_proxy, daemon=True)
        proxy_thread.start()
        
        # Give the proxy a moment to start
        time.sleep(1)
        return True
        
    except Exception as e:
        print(f"Failed to start VNC proxy for {emulator_id}: {e}")
        return False

def stop_vnc_proxy(emulator_id):
    """Stop VNC proxy for an emulator"""
    if emulator_id in vnc_proxies:
        try:
            proxy = vnc_proxies[emulator_id]
            proxy.terminate()
            del vnc_proxies[emulator_id]
            print(f"Stopped VNC proxy for {emulator_id}")
        except Exception as e:
            print(f"Error stopping VNC proxy for {emulator_id}: {e}")

def get_available_proxy_port():
    """Get an available port for WebSocket proxy"""
    import socket
    for port in range(6080, 6180):  # WebSocket proxy port range
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('localhost', port))
            sock.close()
            return port
        except:
            continue
    return None

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

@app.route('/api/containers/discover', methods=['POST'])
def discover_containers():
    """Manually trigger discovery of existing containers"""
    try:
        discover_existing_containers()
        return jsonify({
            "success": True,
            "message": "Container discovery completed",
            "discovered_sessions": list(sessions.keys())
        })
    except Exception as e:
        logger.error(f"Error in container discovery: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

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
        'DEVICE_PORT': '5554',  # Use container's internal port, not random port
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
    
    # Use robust ADB server restart
    logger.info("Setting up ADB connection for new emulator...")
    if not robust_adb_server_restart(adb_server_port):
        logger.warning("Failed to restart ADB server, but container is running")
        # Don't fail the creation, just log the issue
        final_status = "server_failed"
        devices_result = {"success": False, "error": "ADB server failed to start"}
    else:
        # Use robust device detection
        final_status = detect_device_with_retry(adb_server_port, adb_device_port, max_retries=3, retry_delay=2)
        
        # Get current devices list
        devices_result = run_adb_command("devices", ["-P", str(adb_server_port), "devices"], adb_server_port=adb_server_port)
    
    # Log creation info
    logger.info(f"Created Android {android_version} emulator {device_id}")
    logger.info(f"Console: telnet localhost {mapped_ports['console']}")
    logger.info(f"ADB Server Port: {mapped_ports['adb_server']}")
    logger.info(f"Device status: {final_status}")
    
    response_data = {
        'id': session_id,
        'device_id': device_id,
        'android_version': android_version,
        'device_port': mapped_ports['console'],
        'ports': mapped_ports,
        'adb_commands': adb_commands,
        'has_external_adb_server': map_external_adb_server,
        'adb_setup': {
            'server_restart': True,
            'server_port': adb_server_port,
            'devices_output': devices_result,
            'final_device_status': final_status,
            'connection_successful': final_status in ["device", "offline"]
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
        return jsonify({"success": False, "error": "Emulator not found"}), 404
    
    session = sessions[emulator_id]
    vnc_port = session.get('vnc_port')
    
    if not vnc_port or vnc_port == 'unknown':
        return jsonify({"success": False, "error": "VNC not available for this emulator"}), 404
    
    # Check if VNC server is actually running
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', int(vnc_port)))
        sock.close()
        
        if result == 0:
            # VNC server is running, start WebSocket proxy
            proxy_port = get_available_proxy_port()
            if proxy_port and start_vnc_proxy(emulator_id, int(vnc_port), proxy_port):
                session['proxy_port'] = proxy_port
                return jsonify({
                    "success": True,
                    "vnc_port": vnc_port,
                    "proxy_port": proxy_port,
                    "ws_url": f"ws://localhost:{proxy_port}",
                    "direct_vnc": f"vnc://localhost:{vnc_port}",
                    "status": "VNC server running"
                })
            else:
                return jsonify({
                    "success": False, 
                    "error": "Failed to start WebSocket proxy",
                    "vnc_port": vnc_port,
                    "direct_vnc": f"vnc://localhost:{vnc_port}"
                }), 500
        else:
            return jsonify({
                "success": False, 
                "error": "VNC server not responding",
                "vnc_port": vnc_port,
                "direct_vnc": f"vnc://localhost:{vnc_port}"
            }), 503
            
    except Exception as e:
        return jsonify({
            "success": False, 
            "error": f"VNC connection check failed: {str(e)}",
            "vnc_port": vnc_port
        }), 500

@app.route('/api/emulators/<emulator_id>/vnc/status')
def vnc_status(emulator_id):
    """Get detailed VNC status for an emulator"""
    if emulator_id not in sessions:
        return jsonify({"error": "Emulator not found"}), 404
    
    session = sessions[emulator_id]
    container = session.get('container')
    vnc_port = session.get('vnc_port')
    
    if not container:
        return jsonify({"error": "Container not found"}), 404
    
    # Get container logs to check VNC status
    try:
        logs = container.logs(tail=50).decode('utf-8')
        vnc_started = "VNC server started" in logs
        vnc_error = "VNC" in logs and ("error" in logs.lower() or "failed" in logs.lower())
        
        return jsonify({
            "vnc_port": vnc_port,
            "vnc_started": vnc_started,
            "vnc_error": vnc_error,
            "container_running": container.status == 'running',
            "recent_logs": logs.split('\n')[-10:] if logs else []
        })
    except Exception as e:
        return jsonify({"error": f"Failed to get container status: {str(e)}"}), 500

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
    
    logger.info(f"Taking screenshot for emulator {emulator_id} - ADB port: {adb_port}, Server port: {adb_server_port}")
    
    try:
        # Step 1: Restart ADB server robustly
        logger.info("Restarting ADB server for screenshot...")
        if not robust_adb_server_restart(adb_server_port):
            return jsonify({"success": False, "error": "Failed to restart ADB server"})
        
        # Step 2: Detect device with retries
        logger.info("Detecting device...")
        device_status = detect_device_with_retry(adb_server_port, adb_port, max_retries=3, retry_delay=3)
        
        if device_status == "not_found":
            return jsonify({"success": False, "error": f"ADB device localhost:{adb_port} not found after multiple attempts. Emulator may still be booting."})
        elif device_status != "device":
            return jsonify({"success": False, "error": f"Device is {device_status}. Please wait for emulator to fully boot."})
        
        # Step 3: Take screenshot
        logger.info("Device ready, taking screenshot...")
        target_serial = f"localhost:{adb_port}"
        
        cmd = [
            "adb", "-P", str(adb_server_port), 
            "-s", target_serial, 
            "exec-out", "screencap", "-p"
        ]
        
        logger.info(f"Running screenshot command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        
        if result.returncode == 0 and result.stdout:
            # Return screenshot as base64
            import base64
            screenshot_b64 = base64.b64encode(result.stdout).decode()
            logger.info("Screenshot captured successfully")
            return jsonify({"success": True, "screenshot": f"data:image/png;base64,{screenshot_b64}"})
        else:
            return jsonify({"success": False, "error": "Failed to capture screenshot - no data returned"})
                    
    except subprocess.TimeoutExpired:
        logger.error("Screenshot command timed out")
        return jsonify({"success": False, "error": "Screenshot command timed out. Emulator may still be booting."})
                
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"Screenshot command failed: {error_msg}")
        
        # Provide more helpful error messages
        if "device 'localhost:" in error_msg and "not found" in error_msg:
            return jsonify({"success": False, "error": f"ADB device localhost:{adb_port} not found. Emulator may still be starting up."})
        elif "device offline" in error_msg:
            return jsonify({"success": False, "error": "Device is offline. Please wait for emulator to fully boot."})
        else:
            return jsonify({"success": False, "error": f"ADB command failed: {error_msg}"})
                
    except Exception as e:
        logger.error(f"Screenshot error: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/emulators/<emulator_id>/status')
def get_emulator_status(emulator_id):
    """Get emulator status and ADB connectivity"""
    if emulator_id not in sessions:
        return jsonify({"error": "Emulator not found"}), 404
    
    session = sessions[emulator_id]
    adb_port = session['ports']['adb']
    adb_server_port = session['ports']['adb_server']
    
    try:
        # Check container status
        container = session['container']
        container.reload()
        container_status = container.status
        
        # Use robust device detection
        logger.info(f"Checking device status for {emulator_id}")
        device_status = detect_device_with_retry(adb_server_port, adb_port, max_retries=2, retry_delay=1)
        
        device_serial = f"localhost:{adb_port}"
        device_found = device_status != "not_found"
        
        # Try to get emulator properties if connected
        boot_completed = False
        android_version = "unknown"
        
        if device_found and device_status == "device":
            try:
                # Check if boot completed
                boot_cmd = [
                    "adb", "-P", str(adb_server_port), 
                    "-s", device_serial, 
                    "shell", "getprop", "sys.boot_completed"
                ]
                boot_result = subprocess.run(boot_cmd, capture_output=True, text=True, timeout=5)
                if boot_result.returncode == 0 and boot_result.stdout.strip() == "1":
                    boot_completed = True
                
                # Get Android version
                version_cmd = [
                    "adb", "-P", str(adb_server_port), 
                    "-s", device_serial, 
                    "shell", "getprop", "ro.build.version.release"
                ]
                version_result = subprocess.run(version_cmd, capture_output=True, text=True, timeout=5)
                if version_result.returncode == 0:
                    android_version = version_result.stdout.strip()
                    
            except subprocess.TimeoutExpired:
                pass  # Properties check failed, but device is still connected
        
        return jsonify({
            "success": True,
            "emulator_id": emulator_id,
            "device_id": session['device_id'],
            "container_status": container_status,
            "adb": {
                "server_port": adb_server_port,
                "device_port": adb_port,
                "device_serial": device_serial,
                "device_found": device_found,
                "device_status": device_status,
                "boot_completed": boot_completed,
                "android_version": android_version
            },
            "ports": session['ports']
        })
        
    except Exception as e:
        logger.error(f"Error checking emulator status: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/emulators/<emulator_id>/reconnect', methods=['POST'])
def reconnect_emulator(emulator_id):
    """Reconnect to emulator via ADB"""
    if emulator_id not in sessions:
        return jsonify({"error": "Emulator not found"}), 404
    
    session = sessions[emulator_id]
    adb_port = session['ports']['adb']
    adb_server_port = session['ports']['adb_server']
    
    try:
        logger.info(f"Reconnecting emulator {emulator_id}")
        
        # Use robust ADB server restart
        if not robust_adb_server_restart(adb_server_port):
            return jsonify({"success": False, "error": "Failed to restart ADB server"})
        
        # Use robust device detection
        device_status = detect_device_with_retry(adb_server_port, adb_port, max_retries=5, retry_delay=2)
        
        # Get final devices list for reporting
        devices_result = run_adb_command("devices", ["-P", str(adb_server_port), "devices"], adb_server_port=adb_server_port)
        
        return jsonify({
            "success": True,
            "message": "ADB reconnection completed",
            "adb_server_port": adb_server_port,
            "device_port": adb_port,
            "final_device_status": device_status,
            "devices_output": devices_result.get("output", ""),
            "connection_successful": device_status in ["device", "offline"]
        })
        
    except Exception as e:
        logger.error(f"Error reconnecting emulator: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/emulators/<emulator_id>/diagnose')
def diagnose_emulator(emulator_id):
    """Comprehensive diagnostic information for emulator"""
    if emulator_id not in sessions:
        return jsonify({"error": "Emulator not found"}), 404
    
    session = sessions[emulator_id]
    adb_port = session['ports']['adb']
    adb_server_port = session['ports']['adb_server']
    
    diagnostics = {
        "emulator_id": emulator_id,
        "session_info": {
            "device_id": session.get('device_id'),
            "android_version": session.get('android_version'),
            "ports": session.get('ports', {}),
            "has_external_adb_server": session.get('has_external_adb_server', False)
        },
        "tests": {}
    }
    
    try:
        # Test 1: Container status
        container = session['container']
        container.reload()
        diagnostics["tests"]["container_status"] = {
            "status": container.status,
            "running": container.status == "running",
            "ports": container.attrs.get('NetworkSettings', {}).get('Ports', {})
        }
        
        # Test 2: Port connectivity (check if ports are actually listening)
        def check_port(port):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(('localhost', int(port)))
                sock.close()
                return result == 0
            except:
                return False
        
        diagnostics["tests"]["port_connectivity"] = {
            "adb_port": {
                "port": adb_port,
                "listening": check_port(adb_port)
            },
            "adb_server_port": {
                "port": adb_server_port,
                "listening": check_port(adb_server_port)
            }
        }
        
        # Test 3: ADB server status
        set_adb_environment(adb_server_port=adb_server_port)
        
        try:
            # Check if ADB server is running
            start_result = subprocess.run(
                ["adb", "-P", str(adb_server_port), "start-server"], 
                capture_output=True, text=True, timeout=10
            )
            diagnostics["tests"]["adb_server"] = {
                "start_command_success": start_result.returncode == 0,
                "start_output": start_result.stdout,
                "start_error": start_result.stderr
            }
        except Exception as e:
            diagnostics["tests"]["adb_server"] = {
                "error": str(e)
            }
        
        # Test 4: Device listing
        try:
            devices_result = subprocess.run(
                ["adb", "-P", str(adb_server_port), "devices", "-l"], 
                capture_output=True, text=True, timeout=10
            )
            
            devices_info = {
                "command_success": devices_result.returncode == 0,
                "raw_output": devices_result.stdout,
                "devices": []
            }
            
            if devices_result.returncode == 0:
                lines = devices_result.stdout.strip().split('\n')[1:]  # Skip header
                for line in lines:
                    if line.strip():
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            devices_info["devices"].append({
                                "serial": parts[0],
                                "status": parts[1],
                                "details": " ".join(parts[2:]) if len(parts) > 2 else ""
                            })
            
            diagnostics["tests"]["devices"] = devices_info
            
        except Exception as e:
            diagnostics["tests"]["devices"] = {"error": str(e)}
        
        # Test 5: Connection attempt
        try:
            connect_result = subprocess.run(
                ["adb", "-P", str(adb_server_port), "connect", f"localhost:{adb_port}"], 
                capture_output=True, text=True, timeout=15
            )
            diagnostics["tests"]["connection"] = {
                "command_success": connect_result.returncode == 0,
                "output": connect_result.stdout,
                "error": connect_result.stderr
            }
        except Exception as e:
            diagnostics["tests"]["connection"] = {"error": str(e)}
        
        # Test 6: Basic ADB command (if device appears connected)
        device_serial = f"localhost:{adb_port}"
        try:
            shell_result = subprocess.run(
                ["adb", "-P", str(adb_server_port), "-s", device_serial, "shell", "echo", "test"], 
                capture_output=True, text=True, timeout=10
            )
            diagnostics["tests"]["shell_command"] = {
                "command_success": shell_result.returncode == 0,
                "output": shell_result.stdout.strip(),
                "error": shell_result.stderr
            }
        except Exception as e:
            diagnostics["tests"]["shell_command"] = {"error": str(e)}
        
        # Test 7: Boot status (if shell command works)
        try:
            boot_result = subprocess.run(
                ["adb", "-P", str(adb_server_port), "-s", device_serial, "shell", "getprop", "sys.boot_completed"], 
                capture_output=True, text=True, timeout=10
            )
            diagnostics["tests"]["boot_status"] = {
                "command_success": boot_result.returncode == 0,
                "boot_completed": boot_result.stdout.strip() == "1" if boot_result.returncode == 0 else False,
                "output": boot_result.stdout.strip(),
                "error": boot_result.stderr
            }
        except Exception as e:
            diagnostics["tests"]["boot_status"] = {"error": str(e)}
            
    except Exception as e:
        diagnostics["error"] = str(e)
    
    return jsonify(diagnostics)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)