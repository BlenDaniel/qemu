#!/usr/bin/env python3
"""
WebSocket Manager for noVNC connections
Manages websockify processes to bridge WebSocket and VNC connections
"""

import subprocess
import logging
import time
import signal
import os
from threading import Thread, Lock

logger = logging.getLogger(__name__)

# Global registry of active websockify processes
_active_proxies = {}  # {emulator_id: {'process': subprocess.Popen, 'ws_port': int, 'vnc_port': int}}
_proxy_lock = Lock()

def start_websockify(emulator_id, vnc_host, vnc_port, ws_port):
    """
    Start a websockify process for a specific emulator
    
    Args:
        emulator_id: Unique emulator identifier
        vnc_host: Hostname/IP of the VNC server
        vnc_port: Port of the VNC server
        ws_port: WebSocket port for the proxy
        
    Returns:
        dict: {'success': bool, 'ws_port': int, 'message': str}
    """
    with _proxy_lock:
        # Check if proxy already exists
        if emulator_id in _active_proxies:
            existing = _active_proxies[emulator_id]
            if existing['process'].poll() is None:  # Process is still running
                logger.info(f"WebSocket proxy already running for {emulator_id} on port {existing['ws_port']}")
                return {
                    'success': True,
                    'ws_port': existing['ws_port'],
                    'message': 'Proxy already running'
                }
            else:
                # Process died, clean it up
                logger.info(f"Cleaning up dead proxy for {emulator_id}")
                del _active_proxies[emulator_id]
        
        try:
            # Start websockify process
            cmd = [
                'websockify',
                '--web=/opt/noVNC',
                f'{ws_port}',
                f'{vnc_host}:{vnc_port}'
            ]
            
            logger.info(f"Starting websockify: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group for easier cleanup
            )
            
            # Give it a moment to start
            time.sleep(1)
            
            # Check if process started successfully
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                logger.error(f"Websockify failed to start: {stderr.decode()}")
                return {
                    'success': False,
                    'message': f'Failed to start websockify: {stderr.decode()}'
                }
            
            # Store process info
            _active_proxies[emulator_id] = {
                'process': process,
                'ws_port': ws_port,
                'vnc_port': vnc_port,
                'vnc_host': vnc_host
            }
            
            logger.info(f"Started websockify for {emulator_id}: WS port {ws_port} -> VNC {vnc_host}:{vnc_port}")
            
            return {
                'success': True,
                'ws_port': ws_port,
                'message': 'WebSocket proxy started successfully'
            }
            
        except Exception as e:
            logger.error(f"Error starting websockify for {emulator_id}: {str(e)}")
            return {
                'success': False,
                'message': f'Error starting websockify: {str(e)}'
            }

def stop_websockify(emulator_id):
    """
    Stop the websockify process for a specific emulator
    
    Args:
        emulator_id: Unique emulator identifier
        
    Returns:
        dict: {'success': bool, 'message': str}
    """
    with _proxy_lock:
        if emulator_id not in _active_proxies:
            return {
                'success': True,
                'message': 'No proxy running for this emulator'
            }
        
        try:
            proxy_info = _active_proxies[emulator_id]
            process = proxy_info['process']
            
            if process.poll() is None:  # Process is still running
                logger.info(f"Stopping websockify for {emulator_id}")
                
                # Terminate the process group
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    # Give it time to terminate gracefully
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.wait()
                except ProcessLookupError:
                    # Process already terminated
                    pass
            
            del _active_proxies[emulator_id]
            logger.info(f"Stopped websockify for {emulator_id}")
            
            return {
                'success': True,
                'message': 'WebSocket proxy stopped successfully'
            }
            
        except Exception as e:
            logger.error(f"Error stopping websockify for {emulator_id}: {str(e)}")
            return {
                'success': False,
                'message': f'Error stopping websockify: {str(e)}'
            }

def get_websockify_info(emulator_id):
    """
    Get information about the websockify process for an emulator
    
    Args:
        emulator_id: Unique emulator identifier
        
    Returns:
        dict: Process information or None if not running
    """
    with _proxy_lock:
        if emulator_id not in _active_proxies:
            return None
        
        proxy_info = _active_proxies[emulator_id]
        process = proxy_info['process']
        
        # Check if process is still running
        if process.poll() is not None:
            # Process died, clean up
            del _active_proxies[emulator_id]
            return None
        
        return {
            'ws_port': proxy_info['ws_port'],
            'vnc_port': proxy_info['vnc_port'],
            'vnc_host': proxy_info['vnc_host'],
            'pid': process.pid,
            'running': True
        }

def cleanup_all_proxies():
    """
    Stop all active websockify processes
    """
    with _proxy_lock:
        logger.info(f"Cleaning up {len(_active_proxies)} websockify processes")
        
        for emulator_id in list(_active_proxies.keys()):
            try:
                stop_websockify(emulator_id)
            except Exception as e:
                logger.error(f"Error cleaning up proxy for {emulator_id}: {str(e)}")
        
        _active_proxies.clear()
        logger.info("All websockify processes cleaned up")

def get_available_ws_port(base_port=6080):
    """
    Find an available WebSocket port for websockify
    
    Args:
        base_port: Starting port to check from
        
    Returns:
        int: Available port number
    """
    import socket
    
    for port in range(base_port, base_port + 100):
        # Check if port is already in use by our proxies
        if any(info['ws_port'] == port for info in _active_proxies.values()):
            continue
            
        # Check if port is available on the system
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    
    raise RuntimeError("No available ports found for WebSocket proxy")

# Cleanup on module exit
import atexit
atexit.register(cleanup_all_proxies) 