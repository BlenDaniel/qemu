import uuid
import subprocess
import logging
from flask import jsonify, request, abort, render_template

# Import our custom modules
from docker_manager import (
    get_docker_client, discover_existing_containers, create_emulator_container,
    generate_device_id, generate_random_ports, get_container_port_mappings,
    wait_for_container_ports
)
from adb_manager import (
    robust_adb_server_restart, detect_device_with_retry, run_adb_command,
    set_adb_environment, generate_adb_commands, take_screenshot
)
from vnc_manager import (
    get_vnc_connection_info, get_vnc_status
)

logger = logging.getLogger(__name__)

def register_api_routes(app, sessions):
    """Register all API routes with the Flask app"""
    
    # ============================================================================
    # EMULATOR MANAGEMENT API ROUTES
    # ============================================================================

    @app.route('/api/containers/discover', methods=['POST'])
    def discover_containers():
        """Manually trigger discovery of existing containers"""
        try:
            discover_existing_containers(sessions)
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

    @app.route('/api/emulators', methods=['POST'])
    def create_emulator():
        """Create a new emulator"""
        session_id = str(uuid.uuid4())
        device_id = generate_device_id()
        
        # Get request data
        data = request.get_json(silent=True) or {}
        
        # Get Android version (default to 11)
        android_version = str(data.get('android_version', '11'))
        if android_version not in ['11', '14']:
            android_version = '11'  # fallback to Android 11
        
        # Generate random host ports for all services
        ports = generate_random_ports()
        
        # Get custom port mappings if provided, or use defaults
        console_port = data.get('console_port', ports['console_port'])
        adb_port = data.get('adb_port', ports['adb_port'])
        
        # Check if external ADB server is explicitly requested
        map_external_adb_server = data.get('map_adb_server', True)  # Default to True now
        external_adb_server_port = data.get('adb_server_port')
        
        # Prepare port bindings for required ports
        port_bindings = {
            '5554/tcp': console_port,
            '5555/tcp': adb_port,
            '5037/tcp': ports['internal_adb_server_port'],
            '5900/tcp': ports['vnc_port']  # VNC server port
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
            # Create container
            container = create_emulator_container(android_version, device_id, session_id, port_bindings, environment)
        except Exception as e:
            abort(500, description=str(e))

        # Wait until emulator binds ADB port
        if not wait_for_container_ports(container):
            container.stop()
            container.remove()
            abort(500, description="Emulator failed to start properly")

        # Get the actual port mappings
        mapped_ports = get_container_port_mappings(container)
        
        # Generate ADB commands for connecting to this emulator
        adb_commands = generate_adb_commands(mapped_ports)
        
        sessions[session_id] = {
            'container': container,
            'device_port': mapped_ports['console'],
            'ports': mapped_ports,
            'device_id': device_id,
            'android_version': android_version,
            'adb_commands': adb_commands,
            'has_external_adb_server': map_external_adb_server,
            'vnc_port': mapped_ports['vnc'],  # Store VNC port for GUI access
            'is_predefined': False  # Mark as dynamically created
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
        
        # Don't allow deletion of predefined containers
        if session.get('is_predefined', False):
            abort(400, description="Cannot delete predefined containers from docker-compose")
        
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
        """List all emulators - EXCLUDING predefined containers"""
        data = {}
        for sid, session in sessions.items():
            # FILTER OUT PREDEFINED CONTAINERS - only show dynamically created ones
            if session.get('is_predefined', False):
                continue  # Skip predefined containers from docker-compose
                
            container = session['container']
            container.reload()
            
            # Use dynamic port mapping for API-created containers
            mapped_ports = get_container_port_mappings(container)
            
            # Generate or retrieve ADB commands
            adb_commands = session.get('adb_commands', generate_adb_commands(mapped_ports))
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
                'has_external_adb_server': session.get('has_external_adb_server', False),
                'is_predefined': False,  # All returned emulators are dynamically created
                'container_name': container.name
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
    # VNC AND SCREEN ACCESS ROUTES
    # ============================================================================

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
        return jsonify(get_vnc_connection_info(emulator_id, sessions))

    @app.route('/api/emulators/<emulator_id>/vnc/status')
    def vnc_status(emulator_id):
        """Get detailed VNC status for an emulator"""
        return jsonify(get_vnc_status(emulator_id, sessions))

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
        
        result = take_screenshot(adb_server_port, adb_port)
        
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 500

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