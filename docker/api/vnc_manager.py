import threading
import time
import socket
import logging
from websockify import WebSocketProxy

logger = logging.getLogger(__name__)

# Global WebSocket proxy servers
vnc_proxies = {}

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
    for port in range(6080, 6180):  # WebSocket proxy port range
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('localhost', port))
            sock.close()
            return port
        except:
            continue
    return None

def check_vnc_connectivity(vnc_port):
    """Check if VNC server is running and accessible"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', int(vnc_port)))
        sock.close()
        return result == 0
    except Exception:
        return False

def get_vnc_connection_info(emulator_id, sessions):
    """Get VNC connection information for an emulator"""
    if emulator_id not in sessions:
        return {"success": False, "error": "Emulator not found"}
    
    session = sessions[emulator_id]
    vnc_port = session.get('vnc_port')
    
    if not vnc_port or vnc_port == 'unknown':
        return {"success": False, "error": "VNC not available for this emulator"}
    
    # Check if VNC server is actually running
    if check_vnc_connectivity(vnc_port):
        # VNC server is running, start WebSocket proxy
        proxy_port = get_available_proxy_port()
        if proxy_port and start_vnc_proxy(emulator_id, int(vnc_port), proxy_port):
            session['proxy_port'] = proxy_port
            return {
                "success": True,
                "vnc_port": vnc_port,
                "proxy_port": proxy_port,
                "ws_url": f"ws://localhost:{proxy_port}",
                "direct_vnc": f"vnc://localhost:{vnc_port}",
                "status": "VNC server running"
            }
        else:
            return {
                "success": False, 
                "error": "Failed to start WebSocket proxy",
                "vnc_port": vnc_port,
                "direct_vnc": f"vnc://localhost:{vnc_port}"
            }
    else:
        return {
            "success": False, 
            "error": "VNC server not responding",
            "vnc_port": vnc_port,
            "direct_vnc": f"vnc://localhost:{vnc_port}"
        }

def get_vnc_status(emulator_id, sessions):
    """Get detailed VNC status for an emulator"""
    if emulator_id not in sessions:
        return {"error": "Emulator not found"}
    
    session = sessions[emulator_id]
    container = session.get('container')
    vnc_port = session.get('vnc_port')
    
    if not container:
        return {"error": "Container not found"}
    
    # Get container logs to check VNC status
    try:
        logs = container.logs(tail=50).decode('utf-8')
        vnc_started = "VNC server started" in logs
        vnc_error = "VNC" in logs and ("error" in logs.lower() or "failed" in logs.lower())
        
        return {
            "vnc_port": vnc_port,
            "vnc_started": vnc_started,
            "vnc_error": vnc_error,
            "container_running": container.status == 'running',
            "recent_logs": logs.split('\n')[-10:] if logs else [],
            "vnc_connectivity": check_vnc_connectivity(vnc_port) if vnc_port else False
        }
    except Exception as e:
        return {"error": f"Failed to get container status: {str(e)}"}

def cleanup_vnc_proxies():
    """Cleanup all VNC proxies"""
    for emulator_id in list(vnc_proxies.keys()):
        stop_vnc_proxy(emulator_id) 