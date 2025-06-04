import uuid
import subprocess
import logging
from flask import jsonify, request, abort, render_template
import time

# Import our custom modules
from docker_manager import (
    get_docker_client, discover_existing_containers, create_emulator_container,
    generate_device_id, generate_available_ports, get_container_port_mappings,
    wait_for_container_ports, cleanup_orphaned_containers, PREDEFINED_CONTAINERS,
    get_used_ports_from_containers
)
from adb_manager import (
    robust_adb_server_restart, detect_device_with_retry, run_adb_command,
    set_adb_environment, generate_adb_commands, take_screenshot
)
from vnc_manager import (
    get_vnc_connection_info, get_vnc_status
)
from websocket_manager import (
    start_websockify, stop_websockify, get_websockify_info, get_available_ws_port
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
        data = request.json or {}
        android_version = data.get('android_version', '11')
        
        # Validate android version
        if android_version not in ['11', '14']:
            android_version = '11'  # fallback to Android 11
        
        # Clean up any orphaned containers first to free up ports
        cleanup_orphaned_containers()
        
        # Generate unique session ID and device ID
        session_id = str(uuid.uuid4())
        device_id = generate_device_id()
        
        # Generate available ports with conflict avoidance
        try:
            ports = generate_available_ports()
        except Exception as e:
            logger.error(f"Failed to generate available ports: {e}")
            abort(500, description=f"Port allocation failed: {str(e)}")
        
        # Get custom port mappings if provided, or use generated defaults
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
            '5900/tcp': ports['vnc_port'],  # VNC server port
            '6080/tcp': ports['websockify_port']  # Websockify port for noVNC
        }
        
        # If external ADB server was requested, override with specified port
        if map_external_adb_server and external_adb_server_port:
            port_bindings['5037/tcp'] = external_adb_server_port
        
        # Log the port allocation for debugging
        logger.info(f"Creating emulator with port bindings: {port_bindings}")
        
        # Prepare environment variables
        environment = {
            'ANDROID_EMULATOR_WAIT_TIME': '120',
            'ANDROID_EMULATED_DEVICE': android_version,
            'ANDROID_EXTRA_OPTS': f'-gpu swiftshader_indirect -no-snapshot -noaudio -no-boot-anim -no-snapshot-save -avd {device_id}',
            'DEVICE_PORT': '5554',  # Use container's internal port, not random port
            'DEVICE_ID': device_id,
            'ENABLE_VNC': 'true',  # Enable VNC server
            'VNC_PORT': '5900',    # Internal VNC port
            'ENABLE_WEBSOCKIFY': 'true',  # Enable websockify for noVNC
            'WEBSOCKIFY_PORT': '6080'     # Internal websockify port
        }
        
        try:
            # Create container with retry logic for port conflicts
            container = create_emulator_container(android_version, device_id, session_id, port_bindings, environment)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to create emulator: {error_msg}")
            
            # Provide more specific error messages for common issues
            if "port is already allocated" in error_msg:
                abort(500, description="Port allocation conflict. Please try again - the system will automatically select different ports.")
            elif "image" in error_msg.lower() and "not found" in error_msg.lower():
                abort(500, description="Emulator Docker image not found. Please build the required images first.")
            else:
                abort(500, description=f"Emulator creation failed: {error_msg}")

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
            'websockify_port': mapped_ports['websockify'],  # Store websockify port for noVNC
            'is_predefined': False  # Mark as dynamically created
        }
        
        # Setup ADB connection automatically
        adb_server_port = mapped_ports['adb_server']
        adb_device_port = mapped_ports['adb']
        
        # Use robust ADB server restart
        logger.info("Setting up ADB connection for new emulator...")
        logger.info(f"Using ADB server port: {adb_server_port}, device port: {adb_device_port}")
        
        # Give the emulator container a moment to start its services
        time.sleep(3)
        
        if not robust_adb_server_restart(adb_server_port):
            logger.warning("Failed to restart ADB server, but container is running")
            # Don't fail the creation, just log the issue
            final_status = "server_failed"
            devices_result = {"success": False, "error": "ADB server failed to start"}
        else:
            # Use robust device detection with localhost networking
            container_name = container.name
            logger.info(f"Detecting device using localhost networking for container: {container_name}")
            logger.info(f"Connecting to localhost:{adb_device_port} via ADB server on port {adb_server_port}")
            
            final_status = detect_device_with_retry(
                adb_server_port, 
                adb_device_port, 
                max_retries=3, 
                retry_delay=2,
                container_name=container_name  # Pass for logging but use localhost networking
            )
            
            # Get current devices list
            devices_result = run_adb_command("devices", ["-P", str(adb_server_port), "devices"], adb_server_port=adb_server_port)
            
            if final_status == "not_found":
                logger.warning(f"Device not found immediately, but emulator might still be booting")
                logger.info(f"You can manually connect later using: adb connect localhost:{adb_device_port}")
                final_status = "pending"  # Mark as pending instead of not_found
        
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
    # noVNC AND SCREEN ACCESS ROUTES
    # ============================================================================

    @app.route('/api/emulators/<emulator_id>/live_view')
    def live_view(emulator_id):
        """Direct access to noVNC interface via container's built-in websockify port"""
        if emulator_id not in sessions:
            return "Emulator not found", 404
        
        session = sessions[emulator_id]
        device_id = session.get('device_id', 'unknown')
        vnc_port = session.get('vnc_port')
        websockify_port = session.get('websockify_port')
        
        if not vnc_port or not websockify_port:
            return "VNC/WebSocket not available for this emulator", 404
        
        # The emulator container has built-in websockify running on the websockify_port
        # This port is already mapped from container:6080 to host:websockify_port
        logger.info(f"Live view requested for {emulator_id} - using built-in websockify on port {websockify_port}")
        
        # Render noVNC interface using the container's built-in websockify port
        return render_template('novnc_viewer.html', 
                             emulator_id=emulator_id,
                             device_id=device_id,
                             ws_port=websockify_port,  # Use the host-mapped port directly
                             vnc_port=vnc_port)

    @app.route('/api/emulators/<emulator_id>/vnc/test')
    def test_vnc_connection(emulator_id):
        """Test if the VNC/websockify connection is accessible"""
        if emulator_id not in sessions:
            return jsonify({"error": "Emulator not found"}), 404
        
        session = sessions[emulator_id]
        websockify_port = session.get('websockify_port')
        vnc_port = session.get('vnc_port')
        
        if not websockify_port:
            return jsonify({"error": "Websockify port not found"}), 404
        
        import requests
        import socket
        
        test_results = {
            "emulator_id": emulator_id,
            "websockify_port": websockify_port,
            "vnc_port": vnc_port,
            "tests": {}
        }
        
        # Test 1: Check if websockify port is accessible
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex(('localhost', int(websockify_port)))
            sock.close()
            test_results["tests"]["port_accessible"] = result == 0
        except Exception as e:
            test_results["tests"]["port_accessible"] = f"Error: {str(e)}"
        
        # Test 2: Check if noVNC is served on the websockify port
        try:
            response = requests.get(f"http://localhost:{websockify_port}/vnc.html", timeout=5)
            test_results["tests"]["novnc_available"] = response.status_code == 200
            test_results["tests"]["novnc_response_size"] = len(response.content)
        except Exception as e:
            test_results["tests"]["novnc_available"] = f"Error: {str(e)}"
        
        # Test 3: Container status
        try:
            container = session['container']
            container.reload()
            test_results["tests"]["container_status"] = container.status
        except Exception as e:
            test_results["tests"]["container_status"] = f"Error: {str(e)}"
        
        # Test 4: Check if websockify process is running in container
        try:
            container = session['container']
            
            # Use pgrep which is more reliable than ps with grep
            websockify_result = container.exec_run("pgrep -f websockify")
            websockify_running = websockify_result.exit_code == 0
            test_results["tests"]["websockify_process_running"] = websockify_running
            
            if websockify_running:
                # Get detailed process info if running
                ps_result = container.exec_run("ps aux | grep websockify | grep -v grep")
                test_results["tests"]["websockify_processes"] = ps_result.output.decode().strip()
            else:
                test_results["tests"]["websockify_processes"] = "No websockify processes found"
            
            # Test 5: Check VNC server process
            vnc_result = container.exec_run("pgrep -f x11vnc")
            vnc_running = vnc_result.exit_code == 0
            test_results["tests"]["vnc_process_running"] = vnc_running
            
            if vnc_running:
                # Get detailed process info if running
                vnc_ps_result = container.exec_run("ps aux | grep x11vnc | grep -v grep")
                test_results["tests"]["vnc_processes"] = vnc_ps_result.output.decode().strip()
            else:
                test_results["tests"]["vnc_processes"] = "No x11vnc processes found"
            
        except Exception as e:
            test_results["tests"]["websockify_process_running"] = f"Error: {str(e)}"
            test_results["tests"]["vnc_process_running"] = f"Error: {str(e)}"
        
        return jsonify(test_results)

    @app.route('/api/emulators/<emulator_id>/vnc/start', methods=['POST'])
    def start_vnc_proxy(emulator_id):
        """Start websockify proxy for noVNC access"""
        if emulator_id not in sessions:
            return jsonify({"error": "Emulator not found"}), 404
        
        session = sessions[emulator_id]
        vnc_port = session.get('vnc_port')
        
        if not vnc_port:
            return jsonify({"error": "VNC not available for this emulator"}), 404
        
        # Get container for VNC connection
        container = session['container']
        container_name = container.name
        
        try:
            # Check if proxy is already running
            proxy_info = get_websockify_info(emulator_id)
            
            if proxy_info:
                return jsonify({
                    "success": True,
                    "message": "WebSocket proxy already running",
                    "ws_port": proxy_info['ws_port'],
                    "novnc_url": f"/api/emulators/{emulator_id}/live_view"
                })
            
            # Start new proxy
            ws_port = get_available_ws_port()
            result = start_websockify(emulator_id, container_name, vnc_port, ws_port)
            
            if result['success']:
                return jsonify({
                    "success": True,
                    "message": result['message'],
                    "ws_port": result['ws_port'],
                    "novnc_url": f"/api/emulators/{emulator_id}/live_view"
                })
            else:
                return jsonify({
                    "success": False,
                    "error": result['message']
                }), 500
                
        except Exception as e:
            logger.error(f"Error starting VNC proxy for {emulator_id}: {str(e)}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/emulators/<emulator_id>/vnc/stop', methods=['POST'])
    def stop_vnc_proxy(emulator_id):
        """Stop websockify proxy for an emulator"""
        if emulator_id not in sessions:
            return jsonify({"error": "Emulator not found"}), 404
        
        try:
            result = stop_websockify(emulator_id)
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Error stopping VNC proxy for {emulator_id}: {str(e)}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/emulators/<emulator_id>/vnc/status')
    def vnc_proxy_status(emulator_id):
        """Get websockify proxy status for an emulator"""
        if emulator_id not in sessions:
            return jsonify({"error": "Emulator not found"}), 404
        
        try:
            proxy_info = get_websockify_info(emulator_id)
            session = sessions[emulator_id]
            
            if proxy_info:
                return jsonify({
                    "success": True,
                    "running": True,
                    "ws_port": proxy_info['ws_port'],
                    "vnc_port": proxy_info['vnc_port'],
                    "vnc_host": proxy_info['vnc_host'],
                    "pid": proxy_info['pid'],
                    "novnc_url": f"/api/emulators/{emulator_id}/live_view"
                })
            else:
                return jsonify({
                    "success": True,
                    "running": False,
                    "vnc_port": session.get('vnc_port'),
                    "message": "WebSocket proxy not running"
                })
                
        except Exception as e:
            logger.error(f"Error checking VNC proxy status for {emulator_id}: {str(e)}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/emulators/<emulator_id>/vnc/restart', methods=['POST'])
    def restart_vnc_services(emulator_id):
        """Restart VNC and websockify services in the container"""
        if emulator_id not in sessions:
            return jsonify({"error": "Emulator not found"}), 404
        
        session = sessions[emulator_id]
        container = session['container']
        
        try:
            results = {}
            
            # Kill existing VNC and websockify processes
            logger.info(f"Restarting VNC services for {emulator_id}")
            
            # Kill existing processes
            container.exec_run("pkill -f x11vnc || true")
            container.exec_run("pkill -f websockify || true")
            time.sleep(2)
            
            # Start Xvfb if not running
            xvfb_check = container.exec_run("pgrep Xvfb")
            if xvfb_check.exit_code != 0:
                logger.info("Starting Xvfb...")
                container.exec_run("Xvfb :1 -screen 0 1024x768x24 -ac +extension GLX +render -noreset", detach=True)
                time.sleep(2)
            
            # Start window manager if not running
            fluxbox_check = container.exec_run("pgrep fluxbox")
            if fluxbox_check.exit_code != 0:
                logger.info("Starting Fluxbox...")
                container.exec_run("DISPLAY=:1 fluxbox", detach=True)
                time.sleep(2)
            
            # Start VNC server
            logger.info("Starting VNC server...")
            vnc_cmd = "DISPLAY=:1 x11vnc -display :1 -forever -nopw -listen localhost -xkb -rfbport 5900 -shared -permitfiletransfer -tightfilexfer -quiet"
            vnc_result = container.exec_run(vnc_cmd, detach=True)
            results["vnc_started"] = vnc_result.exit_code == 0
            time.sleep(3)
            
            # Start websockify
            logger.info("Starting websockify...")
            websockify_cmd = "websockify --web=/opt/noVNC --target-config=/dev/null 6080 localhost:5900"
            websockify_result = container.exec_run(websockify_cmd, detach=True)
            results["websockify_started"] = websockify_result.exit_code == 0
            time.sleep(3)
            
            # Verify services are running
            vnc_check = container.exec_run("pgrep -f x11vnc")
            websockify_check = container.exec_run("pgrep -f websockify")
            
            results["vnc_running"] = vnc_check.exit_code == 0
            results["websockify_running"] = websockify_check.exit_code == 0
            
            # Get process details if running
            if results["vnc_running"]:
                vnc_ps = container.exec_run("ps aux | grep x11vnc | grep -v grep")
                results["vnc_process_details"] = vnc_ps.output.decode().strip()
            
            if results["websockify_running"]:
                ws_ps = container.exec_run("ps aux | grep websockify | grep -v grep") 
                results["websockify_process_details"] = ws_ps.output.decode().strip()
            
            return jsonify({
                "success": True,
                "message": "VNC services restart attempted",
                "results": results,
                "vnc_port": session.get('vnc_port'),
                "websockify_port": session.get('websockify_port')
            })
            
        except Exception as e:
            logger.error(f"Error restarting VNC services for {emulator_id}: {str(e)}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/emulators/<emulator_id>/vnc/proxy')
    def vnc_proxy_page(emulator_id):
        """Proxy noVNC page to avoid CORS issues"""
        if emulator_id not in sessions:
            return "Emulator not found", 404
        
        session = sessions[emulator_id]
        websockify_port = session.get('websockify_port')
        
        if not websockify_port:
            return "Websockify port not found", 404
        
        import requests
        try:
            # Fetch the noVNC page from the container's websockify
            response = requests.get(f"http://localhost:{websockify_port}/vnc.html", timeout=10)
            
            if response.status_code == 200:
                # Modify the content to use the correct WebSocket URL
                content = response.text
                
                # Replace WebSocket connections to use the correct host and port
                content = content.replace('ws://localhost:6080', f'ws://localhost:{websockify_port}')
                content = content.replace('ws://127.0.0.1:6080', f'ws://localhost:{websockify_port}')
                
                return content, 200, {'Content-Type': 'text/html'}
            else:
                return f"Failed to load noVNC: HTTP {response.status_code}", 500
                
        except Exception as e:
            logger.error(f"Error proxying noVNC page for {emulator_id}: {str(e)}")
            return f"Error loading noVNC: {str(e)}", 500

    # ============================================================================
    # HEALTH CHECK AND DEBUGGING API ROUTES
    # ============================================================================

    @app.route('/api/health', methods=['GET'])
    def system_health():
        """Health check endpoint that reports system status and port usage"""
        try:
            # Check Docker connection
            docker_client = get_docker_client()
            docker_status = "connected" if docker_client else "disconnected"
            
            # Get port usage
            used_ports = get_used_ports_from_containers()
            
            # Count containers
            container_counts = {"total": 0, "running": 0, "emulator": 0}
            if docker_client:
                all_containers = docker_client.containers.list(all=True)
                container_counts["total"] = len(all_containers)
                
                running_containers = docker_client.containers.list()
                container_counts["running"] = len(running_containers)
                
                emulator_containers = [c for c in all_containers if c.name.startswith('emu_') or 'emulator' in c.name.lower()]
                container_counts["emulator"] = len(emulator_containers)
            
            # Check session status
            session_count = len(sessions)
            
            health_status = {
                "status": "healthy" if docker_status == "connected" else "unhealthy",
                "timestamp": time.time(),
                "docker": {
                    "status": docker_status,
                    "containers": container_counts
                },
                "ports": {
                    "used_count": len(used_ports),
                    "used_ports": sorted(list(used_ports)) if len(used_ports) < 50 else f"{len(used_ports)} ports in use"
                },
                "sessions": {
                    "active_count": session_count,
                    "session_ids": list(sessions.keys())
                },
                "port_ranges": {
                    "console": "5000-5999",
                    "adb": "6000-6999",
                    "adb_server": "7000-7999",
                    "vnc": "5900-5950",
                    "websockify": "6200-6300"
                }
            }
            
            return jsonify(health_status)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                "status": "error",
                "timestamp": time.time(),
                "error": str(e)
            }), 500

    @app.route('/api/cleanup', methods=['POST'])
    def manual_cleanup():
        """Manual cleanup endpoint for orphaned containers"""
        try:
            logger.info("Manual cleanup requested via API")
            cleanup_orphaned_containers()
            
            return jsonify({
                "success": True,
                "message": "Cleanup completed successfully"
            })
            
        except Exception as e:
            logger.error(f"Manual cleanup failed: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/debug/test-networking', methods=['GET'])
    def test_networking():
        """Test container networking and connectivity"""
        results = {}
        
        for session_id, session in sessions.items():
            container = session['container']
            container_name = container.name
            is_predefined = session.get('is_predefined', False)
            
            test_result = {
                "container_name": container_name,
                "is_predefined": is_predefined,
                "tests": {}
            }
            
            if not is_predefined:
                # Test port connectivity using container networking
                import socket
                
                # Test ADB port (5555 internal)
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)
                    result = sock.connect_ex((container_name, 5555))
                    sock.close()
                    test_result["tests"]["adb_port_5555"] = result == 0
                except Exception as e:
                    test_result["tests"]["adb_port_5555"] = f"Error: {str(e)}"
                
                # Test VNC port (5900 internal)
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)
                    result = sock.connect_ex((container_name, 5900))
                    sock.close()
                    test_result["tests"]["vnc_port_5900"] = result == 0
                except Exception as e:
                    test_result["tests"]["vnc_port_5900"] = f"Error: {str(e)}"
                
                # Test ADB connect
                try:
                    adb_server_port = session['ports']['adb_server']
                    connect_result = run_adb_command(
                        "connect", 
                        ["-P", str(adb_server_port), "connect", f"{container_name}:5555"],
                        adb_server_port=adb_server_port
                    )
                    test_result["tests"]["adb_connect"] = connect_result
                except Exception as e:
                    test_result["tests"]["adb_connect"] = f"Error: {str(e)}"
            
            results[session_id] = test_result
        
        return jsonify({
            "success": True,
            "message": "Networking tests completed",
            "results": results
        })

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

    # Legacy VNC routes (deprecated - but kept for compatibility)
    @app.route('/vnc/<emulator_id>')
    def vnc_viewer(emulator_id):
        """Legacy VNC viewer - redirects to live view"""
        return live_view(emulator_id)

    @app.route('/api/emulators/<emulator_id>/vnc')
    def vnc_proxy(emulator_id):
        """Legacy VNC proxy info - redirects to status"""
        return vnc_proxy_status(emulator_id)

    @app.route('/api/emulators/<emulator_id>/screenshot')
    def get_screenshot(emulator_id):
        """Get screenshot from emulator"""
        if emulator_id not in sessions:
            return jsonify({"error": "Emulator not found"}), 404
        
        session = sessions[emulator_id]
        adb_port = session['ports']['adb']
        adb_server_port = session['ports']['adb_server']
        
        logger.info(f"Taking screenshot for emulator {emulator_id} - ADB port: {adb_port}, Server port: {adb_server_port}")
        
        # Get container name for Docker networking (for dynamic containers)
        container = session['container']
        container_name = container.name if not session.get('is_predefined', False) else None
        
        result = take_screenshot(adb_server_port, adb_port, container_name)
        
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
            
            # Use robust device detection with container networking
            logger.info(f"Checking device status for {emulator_id}")
            container_name = container.name if not session.get('is_predefined', False) else None
            device_status = detect_device_with_retry(
                adb_server_port, 
                adb_port, 
                max_retries=2, 
                retry_delay=1,
                container_name=container_name
            )
            
            device_serial = f"localhost:{adb_port}"
            device_found = device_status != "not_found"
            
            # Try to get emulator properties if connected
            boot_completed = False
            android_version = "unknown"
            
            if device_found and device_status == "device":
                try:
                    # Use container networking for ADB commands if it's a dynamic container
                    if container_name:
                        target_device = f"{container_name}:5555"
                    else:
                        target_device = device_serial
                    
                    # Check if boot completed
                    boot_cmd = [
                        "adb", "-P", str(adb_server_port), 
                        "-s", target_device, 
                        "shell", "getprop", "sys.boot_completed"
                    ]
                    boot_result = subprocess.run(boot_cmd, capture_output=True, text=True, timeout=5)
                    if boot_result.returncode == 0 and boot_result.stdout.strip() == "1":
                        boot_completed = True
                    
                    # Get Android version
                    version_cmd = [
                        "adb", "-P", str(adb_server_port), 
                        "-s", target_device, 
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
                    "android_version": android_version,
                    "container_name": container_name
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
            
            # Use robust device detection with container networking
            container = session['container']
            container_name = container.name if not session.get('is_predefined', False) else None
            device_status = detect_device_with_retry(
                adb_server_port, 
                adb_port, 
                max_retries=5, 
                retry_delay=2,
                container_name=container_name
            )
            
            # Get final devices list for reporting
            devices_result = run_adb_command("devices", ["-P", str(adb_server_port), "devices"], adb_server_port=adb_server_port)
            
            return jsonify({
                "success": True,
                "message": "ADB reconnection completed",
                "adb_server_port": adb_server_port,
                "device_port": adb_port,
                "final_device_status": device_status,
                "devices_output": devices_result.get("output", ""),
                "connection_successful": device_status in ["device", "offline"],
                "container_name": container_name
            })
            
        except Exception as e:
            logger.error(f"Error reconnecting emulator: {str(e)}")
            return jsonify({"success": False, "error": str(e)})

    @app.route('/api/emulators/<emulator_id>/wake', methods=['POST'])
    def wake_emulator(emulator_id):
        """Wake up the emulator display and send some input to make it show content"""
        if emulator_id not in sessions:
            return jsonify({"error": "Emulator not found"}), 404
        
        session = sessions[emulator_id]
        adb_port = session['ports']['adb']
        adb_server_port = session['ports']['adb_server']
        
        try:
            logger.info(f"Waking up emulator {emulator_id} display...")
            
            commands = []
            
            # 1. Wake up the device (turn on screen)
            wake_cmd = ["adb", "-P", str(adb_server_port), "shell", "input", "keyevent", "KEYCODE_WAKEUP"]
            commands.append(("wake_screen", wake_cmd))
            
            # 2. Unlock the device (swipe up)
            unlock_cmd = ["adb", "-P", str(adb_server_port), "shell", "input", "swipe", "200", "800", "200", "200"]
            commands.append(("unlock_swipe", unlock_cmd))
            
            # 3. Send home key to go to launcher
            home_cmd = ["adb", "-P", str(adb_server_port), "shell", "input", "keyevent", "KEYCODE_HOME"]
            commands.append(("home_key", home_cmd))
            
            # 4. Check if boot is completed
            boot_cmd = ["adb", "-P", str(adb_server_port), "shell", "getprop", "sys.boot_completed"]
            commands.append(("boot_check", boot_cmd))
            
            # 5. Get screen density for better scaling
            density_cmd = ["adb", "-P", str(adb_server_port), "shell", "wm", "density"]
            commands.append(("density_check", density_cmd))
            
            results = {}
            
            for name, cmd in commands:
                try:
                    logger.info(f"Running {name}: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    results[name] = {
                        "returncode": result.returncode,
                        "stdout": result.stdout.strip(),
                        "stderr": result.stderr.strip() if result.stderr else ""
                    }
                    # Small delay between commands
                    time.sleep(1)
                except subprocess.TimeoutExpired:
                    results[name] = {"error": "Command timed out"}
                except Exception as e:
                    results[name] = {"error": str(e)}
            
            return jsonify({
                "success": True,
                "message": "Emulator wake commands sent",
                "emulator_id": emulator_id,
                "commands_run": results
            })
            
        except Exception as e:
            logger.error(f"Error waking emulator: {str(e)}")
            return jsonify({"success": False, "error": str(e)}) 