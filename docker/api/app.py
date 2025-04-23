import uuid
from flask import Flask, jsonify, request, abort
import docker
import time
import uuid
import subprocess
import os
import shutil

app = Flask(__name__)
client = docker.from_env()
EMULATOR_IMAGE = "qemu-emulator"

# In-memory mapping of emulator sessions: id -> container
sessions = {}

# Check if ADB is in PATH
def is_adb_available():
    return shutil.which('adb') is not None

# Execute ADB command with error handling
def execute_adb_command(cmd_args, check=False):
    if not is_adb_available():
        return {"error": "ADB command not found in PATH"}, False
    
    try:
        process = subprocess.run(
            cmd_args,
            check=check,
            capture_output=True,
            text=True
        )
        return process.stdout.strip(), True
    except Exception as e:
        return {"error": f"ADB command failed: {str(e)}"}, False

@app.route('/emulators', methods=['POST'])
def create_emulator():
    session_id = str(uuid.uuid4())
    try:
        # Run container with specific ports published randomly on the host
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
        if ports.get('5555/tcp') and ports['5555/tcp'] is not None:
            break
        time.sleep(1)

    sessions[session_id] = container
    
    # Format the response with connection instructions
    port_mappings = ports.get('5555/tcp', [])
    adb_port = port_mappings[0]['HostPort'] if port_mappings else None
    adb_command = f"adb connect localhost:{adb_port}" if adb_port else "Unknown"
    
    # Automatically connect to the emulator
    connection_status = "Not attempted"
    if adb_port:
        if not is_adb_available():
            connection_status = "ADB command not found in PATH"
        else:
            try:
                # Ensure ADB server is running
                output, success = execute_adb_command(["adb", "start-server"])
                if not success:
                    connection_status = f"Error starting ADB server: {output.get('error', 'Unknown error')}"
                else:
                    # Try to connect multiple times (emulator might not be ready immediately)
                    max_retries = 5
                    for attempt in range(1, max_retries + 1):
                        # Wait a bit to give the emulator time to initialize
                        time.sleep(3)
                        
                        # Connect to the emulator
                        output, success = execute_adb_command(["adb", "connect", f"localhost:{adb_port}"])
                        
                        if success and "connected" in output.lower() and "failed" not in output.lower():
                            connection_status = f"Connected successfully on attempt {attempt}/{max_retries}"
                            break
                        
                        # If we're on the last attempt and still not connected, report the issue
                        if attempt == max_retries:
                            connection_status = f"Failed to connect after {max_retries} attempts: {output}"
            except Exception as e:
                connection_status = f"Error during connection: {str(e)}"
    
    response = {
        'id': session_id, 
        'ports': ports,
        'connection_info': {
            'adb_command': adb_command,
            'mapped_adb_port': adb_port,
            'auto_connection_status': connection_status
        }
    }
    
    return jsonify(response), 201


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
    
    # First get list of current ADB devices to check status
    device_status = {}
    if is_adb_available():
        output, success = execute_adb_command(["adb", "devices"])
        if success:
            # Parse device status from adb output
            for line in output.strip().split('\n')[1:]:  # Skip the first line (header)
                if '\t' in line:
                    device, status = line.split('\t')
                    if 'localhost:' in device:
                        port = device.split(':')[1].strip()
                        device_status[port] = status
    
    for sid, container in sessions.items():
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        adb_port = None
        connection_status = "Unknown"
        
        if ports.get('5555/tcp'):
            adb_port = ports['5555/tcp'][0]['HostPort']
            
            if not is_adb_available():
                connection_status = "ADB command not found in PATH"
            else:
                # Check if device is already connected and its status
                if adb_port in device_status:
                    connection_status = device_status[adb_port]
                    
                    # If device is offline, try to reconnect automatically
                    if connection_status.lower() == 'offline':
                        try:
                            # Kill and restart ADB server
                            execute_adb_command(["adb", "kill-server"])
                            execute_adb_command(["adb", "start-server"])
                            time.sleep(1)
                            
                            # Try to reconnect
                            output, success = execute_adb_command(["adb", "connect", f"localhost:{adb_port}"])
                            
                            # Check if reconnection worked
                            if success and "connected" in output.lower() and "failed" not in output.lower():
                                connection_status = "reconnected"
                            else:
                                connection_status = f"offline (reconnect failed: {output})"
                        except Exception as e:
                            connection_status = f"offline (reconnect error: {str(e)})"
                else:
                    # If device is not in the list, try to connect
                    try:
                        output, success = execute_adb_command(["adb", "connect", f"localhost:{adb_port}"])
                        if success and "connected" in output.lower() and "failed" not in output.lower():
                            connection_status = "newly connected"
                        else:
                            connection_status = f"connection failed: {output}"
                    except Exception as e:
                        connection_status = f"connection error: {str(e)}"
            
        data[sid] = {
            'ports': ports,
            'connection_info': {
                'adb_command': f"adb connect localhost:{adb_port}" if adb_port else "Unknown",
                'mapped_adb_port': adb_port,
                'connection_status': connection_status
            }
        }
    return jsonify(data)

@app.route('/healthcheck', methods=['GET'])
def healthcheck():
    # Check if API server is running
    api_status = "healthy"
    
    # Check if ADB is available
    adb_status = "available" if is_adb_available() else "not found in PATH"
    
    # Check if emulator containers are running
    containers_status = []
    for sid, container in sessions.items():
        try:
            container.reload()
            status = container.status
            containers_status.append({
                "id": sid,
                "status": status
            })
        except Exception as e:
            containers_status.append({
                "id": sid,
                "status": f"error: {str(e)}"
            })
    
    # Check ADB connections
    connections = []
    if is_adb_available():
        output, success = execute_adb_command(["adb", "devices"])
        if success:
            # Parse the output
            for line in output.strip().split('\n')[1:]:
                if '\t' in line:
                    device, status = line.split('\t')
                    connections.append({
                        "device": device,
                        "status": status
                    })
        else:
            api_status = f"error getting ADB status: {output.get('error', 'Unknown error')}"
    else:
        api_status = "ADB not available"
    
    # Count statistics about connections
    stats = {
        "total_emulators": len(sessions),
        "running_containers": sum(1 for c in containers_status if c["status"] == "running"),
        "connected_devices": sum(1 for c in connections if c["status"] == "device"),
        "offline_devices": sum(1 for c in connections if c["status"] == "offline"),
        "adb_status": adb_status
    }
    
    # Auto-fix offline devices if requested
    fix = request.args.get('fix', 'false').lower() == 'true'
    fix_results = []
    
    if fix and stats["offline_devices"] > 0 and is_adb_available():
        # Restart ADB server if there are offline devices
        try:
            execute_adb_command(["adb", "kill-server"])
            time.sleep(1)
            execute_adb_command(["adb", "start-server"])
            
            time.sleep(2)
            
            # Try to reconnect each device
            for connection in connections:
                if connection["status"] == "offline" and "localhost:" in connection["device"]:
                    device = connection["device"]
                    output, success = execute_adb_command(["adb", "connect", device])
                    fix_results.append({
                        "device": device,
                        "result": output if success else output.get('error', 'Unknown error')
                    })
        except Exception as e:
            fix_results.append({
                "error": f"Error during fix: {str(e)}"
            })
    
    return jsonify({
        "status": api_status,
        "timestamp": time.time(),
        "containers": containers_status,
        "connections": connections,
        "stats": stats,
        "fix_results": fix_results if fix else []
    })

if __name__ == '__main__':
    # Default to port 5001, but allow override via environment variable
    port = int(os.environ.get('API_PORT', 5001))
    
    # Check ADB availability at startup
    if not is_adb_available():
        print("WARNING: ADB command not found in PATH. Some functionality will be limited.")
        print(f"Current PATH: {os.environ.get('PATH', 'Not set')}")
    else:
        print("ADB found in PATH.")
    
    app.run(host='0.0.0.0', port=port)
