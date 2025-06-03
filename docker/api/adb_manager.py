import subprocess
import platform
import time
import logging
import os
import shlex

logger = logging.getLogger(__name__)

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

def detect_device_with_retry(adb_server_port, device_port, max_retries=10, retry_delay=3, container_host=None, container_name=None):
    """Detect device with multiple retries and better error handling"""
    
    # For dynamically created containers, use container name for networking
    if container_name and not container_host:
        # Extract container name for Docker networking
        # Container names like "emu_deviceid_sessionid" should be accessible directly
        target_serial = f"{container_name}:5555"  # Always use internal port 5555
        logger.info(f"Using Docker container networking: {container_name}:5555")
    elif container_host:
        # For predefined containers from docker-compose
        target_serial = f"{container_host}:{device_port}"
        logger.info(f"Using Docker service networking: {container_host}:{device_port}")
    else:
        # Fallback to localhost (host networking)
        target_serial = f"localhost:{device_port}"
        logger.info(f"Using localhost networking: localhost:{device_port}")
    
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
                                
                                # Check for exact match or emulator serial format
                                if (serial == target_serial or 
                                    (container_name and serial.startswith("emulator-")) or
                                    (target_serial.endswith(":5555") and serial.startswith("emulator-"))):
                                    logger.info(f"Found device {serial} with status: {status}")
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

def setup_adb_for_existing_container(session_id, config):
    """Set up ADB connection for an existing container"""
    try:
        # For predefined containers from docker-compose, we need to connect to the host-mapped ports
        # since the ADB server is running inside the emulator container
        adb_server_port = config['ports']['adb_server']  # Use host-mapped port (5037 or 6037)
        adb_device_port = config['ports']['adb']  # Use host-mapped port (5555 or 6655)
        
        logger.info(f"Setting up ADB for {session_id} - server port: {adb_server_port}, device port: {adb_device_port}")
        
        # First, try to restart our ADB server to ensure clean state
        logger.info("Restarting local ADB server for clean connection")
        if not robust_adb_server_restart(adb_server_port):
            logger.warning(f"Failed to restart ADB server for {session_id}, trying direct connection")
        
        # Try to connect to the emulator running inside the container
        # The emulator container exposes its ADB device port to the host
        device_status = detect_device_with_retry(
            adb_server_port=adb_server_port, 
            device_port=adb_device_port, 
            max_retries=5, 
            retry_delay=3,
            container_host=None  # Use localhost since we're connecting to host-mapped ports
        )
        
        if device_status in ["device", "offline"]:
            logger.info(f"Successfully connected to device for {session_id} with status: {device_status}")
            return True
        else:
            logger.warning(f"Failed to connect to device for {session_id}. Status: {device_status}")
            # Don't fail completely - the emulator might still be booting
            return True  # Return True to allow registration
        
    except Exception as e:
        logger.error(f"Failed to setup ADB for {session_id}: {e}")
        return False

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

def generate_adb_commands(mapped_ports):
    """Generate ADB commands for connecting to an emulator"""
    return {
        'connect': f"adb connect localhost:{mapped_ports['adb']}",
        'server': f"adb -P {mapped_ports['adb_server']} devices",
        'set_server_unix': f"export ANDROID_ADB_SERVER_PORT={mapped_ports['adb_server']}",
        'set_server_windows': f"$env:ANDROID_ADB_SERVER_PORT = \"{mapped_ports['adb_server']}\"",
        'kill_and_restart_server': f"adb kill-server && adb -P {mapped_ports['adb_server']} start-server"
    }

def take_screenshot(adb_server_port, adb_port, container_name=None):
    """Take a screenshot from an emulator via ADB"""
    try:
        # Step 1: Restart ADB server robustly
        logger.info("Restarting ADB server for screenshot...")
        if not robust_adb_server_restart(adb_server_port):
            return {"success": False, "error": "Failed to restart ADB server"}
        
        # Step 2: Detect device with retries
        logger.info("Detecting device...")
        device_status = detect_device_with_retry(
            adb_server_port, 
            adb_port, 
            max_retries=3, 
            retry_delay=3,
            container_name=container_name
        )
        
        if device_status == "not_found":
            return {"success": False, "error": f"ADB device not found after multiple attempts. Emulator may still be booting."}
        elif device_status != "device":
            return {"success": False, "error": f"Device is {device_status}. Please wait for emulator to fully boot."}
        
        # Step 3: Take screenshot
        logger.info("Device ready, taking screenshot...")
        
        # Use container networking if available
        if container_name:
            target_serial = f"{container_name}:5555"
        else:
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
            return {"success": True, "screenshot": f"data:image/png;base64,{screenshot_b64}"}
        else:
            return {"success": False, "error": "Failed to capture screenshot - no data returned"}
                    
    except subprocess.TimeoutExpired:
        logger.error("Screenshot command timed out")
        return {"success": False, "error": "Screenshot command timed out. Emulator may still be booting."}
                
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"Screenshot command failed: {error_msg}")
        
        # Provide more helpful error messages
        if "device" in error_msg and "not found" in error_msg:
            return {"success": False, "error": f"ADB device not found. Emulator may still be starting up."}
        elif "device offline" in error_msg:
            return {"success": False, "error": "Device is offline. Please wait for emulator to fully boot."}
        else:
            return {"success": False, "error": f"ADB command failed: {error_msg}"}
                
    except Exception as e:
        logger.error(f"Screenshot error: {str(e)}")
        return {"success": False, "error": str(e)} 