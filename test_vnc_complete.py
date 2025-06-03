#!/usr/bin/env python3
"""
Complete VNC functionality test script.
This script validates the entire VNC setup including WebSocket proxies, 
VNC server connectivity, and fallback mechanisms.
"""

import requests
import json
import time
import socket
import subprocess
import sys
import os
from datetime import datetime

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def check_port_open(host, port, timeout=5):
    """Check if a port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        log(f"Port check error: {e}")
        return False

def check_api_health():
    """Check if the API is running"""
    try:
        response = requests.get('http://localhost:5001/health', timeout=10)
        return response.status_code == 200
    except Exception as e:
        log(f"API health check failed: {e}")
        return False

def check_docker_status():
    """Check Docker container status"""
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        log(f"Docker containers status:")
        log(result.stdout)
        return 'qemu-main-api-1' in result.stdout
    except Exception as e:
        log(f"Docker status check failed: {e}")
        return False

def test_vnc_api_endpoints():
    """Test VNC-related API endpoints"""
    log("Testing VNC API endpoints...")
    
    # Get list of emulators
    try:
        response = requests.get('http://localhost:5001/api/emulators', timeout=10)
        if response.status_code != 200:
            log(f"❌ Failed to get emulators list: {response.status_code}")
            return False
            
        emulators = response.json()
        log(f"Found {len(emulators)} emulators")
        
        if not emulators:
            log("❌ No emulators found - creating test emulator...")
            create_response = requests.post(
                'http://localhost:5001/api/emulators',
                json={"android_version": "11"},
                timeout=30
            )
            if create_response.status_code not in [200, 201]:
                log(f"❌ Failed to create emulator: {create_response.status_code}")
                return False
                
            time.sleep(5)  # Wait for emulator to start
            
            # Get updated list
            response = requests.get('http://localhost:5001/api/emulators', timeout=10)
            emulators = response.json()
        
        # Test VNC endpoints for each emulator
        for emulator in emulators:
            emulator_id = emulator.get('id')
            if not emulator_id:
                continue
                
            log(f"Testing VNC endpoints for emulator: {emulator_id}")
            
            # Test VNC connection info
            vnc_response = requests.get(f'http://localhost:5001/api/emulators/{emulator_id}/vnc', timeout=10)
            log(f"VNC endpoint response: {vnc_response.status_code}")
            
            if vnc_response.status_code == 200:
                vnc_data = vnc_response.json()
                log(f"✅ VNC data: {json.dumps(vnc_data, indent=2)}")
                
                # Test VNC status
                status_response = requests.get(f'http://localhost:5001/api/emulators/{emulator_id}/vnc/status', timeout=10)
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    log(f"✅ VNC status: {json.dumps(status_data, indent=2)}")
                else:
                    log(f"❌ VNC status failed: {status_response.status_code}")
                
                # Test screenshot fallback
                screenshot_response = requests.get(f'http://localhost:5001/api/emulators/{emulator_id}/screenshot', timeout=15)
                if screenshot_response.status_code == 200:
                    log("✅ Screenshot fallback working")
                else:
                    log(f"❌ Screenshot fallback failed: {screenshot_response.status_code}")
                
                # Test WebSocket proxy if available
                if vnc_data.get('success') and vnc_data.get('proxy_port'):
                    proxy_port = vnc_data['proxy_port']
                    log(f"Testing WebSocket proxy on port {proxy_port}")
                    if check_port_open('localhost', proxy_port):
                        log(f"✅ WebSocket proxy port {proxy_port} is open")
                    else:
                        log(f"❌ WebSocket proxy port {proxy_port} is not accessible")
                
            else:
                log(f"❌ VNC endpoint failed: {vnc_response.status_code}")
                try:
                    error_data = vnc_response.json()
                    log(f"Error details: {json.dumps(error_data, indent=2)}")
                except:
                    log(f"Error response: {vnc_response.text}")
        
        return True
        
    except Exception as e:
        log(f"❌ VNC API test failed: {e}")
        return False

def test_vnc_viewer_page():
    """Test VNC viewer web page"""
    try:
        # Get emulators first
        response = requests.get('http://localhost:5001/api/emulators', timeout=10)
        emulators = response.json()
        
        if not emulators:
            log("❌ No emulators available for VNC viewer test")
            return False
            
        emulator_id = emulators[0].get('id')
        log(f"Testing VNC viewer page for emulator: {emulator_id}")
        
        viewer_response = requests.get(f'http://localhost:5001/vnc/{emulator_id}', timeout=10)
        
        if viewer_response.status_code == 200:
            log("✅ VNC viewer page accessible")
            
            # Check if the page contains expected elements
            content = viewer_response.text
            if 'noVNC' in content or 'VNC' in content:
                log("✅ VNC viewer page contains VNC references")
            else:
                log("❌ VNC viewer page missing VNC content")
                
            return True
        else:
            log(f"❌ VNC viewer page failed: {viewer_response.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ VNC viewer page test failed: {e}")
        return False

def test_direct_vnc_connections():
    """Test direct VNC server connections"""
    log("Testing direct VNC server connections...")
    
    # Common VNC ports to check
    vnc_ports = [5901, 5902, 5900, 6080, 6081]
    
    for port in vnc_ports:
        if check_port_open('localhost', port):
            log(f"✅ VNC/Proxy server found on port {port}")
        else:
            log(f"❌ No VNC/Proxy server on port {port}")

def main():
    """Main test function"""
    log("=" * 60)
    log("VNC Complete Functionality Test")
    log("=" * 60)
    
    # Basic health checks
    log("Step 1: Basic health checks")
    if not check_api_health():
        log("❌ API is not running - please start the Docker containers")
        return False
    log("✅ API is running")
    
    if not check_docker_status():
        log("❌ Docker containers not properly running")
        return False
    log("✅ Docker containers are running")
    
    # Test VNC API endpoints
    log("\nStep 2: Testing VNC API endpoints")
    if not test_vnc_api_endpoints():
        log("❌ VNC API tests failed")
        return False
    log("✅ VNC API tests passed")
    
    # Test VNC viewer page
    log("\nStep 3: Testing VNC viewer web page")
    if not test_vnc_viewer_page():
        log("❌ VNC viewer page tests failed")
        return False
    log("✅ VNC viewer page tests passed")
    
    # Test direct VNC connections
    log("\nStep 4: Testing direct VNC connections")
    test_direct_vnc_connections()
    
    log("\n" + "=" * 60)
    log("VNC functionality test completed!")
    log("=" * 60)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 