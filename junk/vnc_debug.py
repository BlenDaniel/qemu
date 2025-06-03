#!/usr/bin/env python3
"""
VNC Debug and Configuration Script
Helps identify and fix VNC connectivity issues
"""

import subprocess
import socket
import requests
import json
import time
import sys

def check_docker_logs():
    """Check Docker container logs for VNC-related issues"""
    print("\n=== DOCKER LOGS ANALYSIS ===")
    
    containers = ['qemu-main-api-1', 'qemu-main-emulator-1', 'qemu-main-emulator14-1']
    
    for container in containers:
        try:
            print(f"\n--- {container} logs ---")
            result = subprocess.run(['docker', 'logs', '--tail', '20', container], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(result.stdout)
                if result.stderr:
                    print("STDERR:", result.stderr)
            else:
                print(f"Failed to get logs for {container}")
        except Exception as e:
            print(f"Error getting logs for {container}: {e}")

def check_container_processes():
    """Check what processes are running inside containers"""
    print("\n=== CONTAINER PROCESSES ===")
    
    containers = ['qemu-main-emulator-1', 'qemu-main-emulator14-1']
    
    for container in containers:
        try:
            print(f"\n--- {container} processes ---")
            result = subprocess.run(['docker', 'exec', container, 'ps', 'aux'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"Failed to check processes in {container}")
        except Exception as e:
            print(f"Error checking processes in {container}: {e}")

def check_vnc_ports():
    """Check VNC port availability"""
    print("\n=== VNC PORT ANALYSIS ===")
    
    # Check host ports
    host_ports = [5901, 5902, 6080, 6081, 6082]
    print("\nHost port status:")
    for port in host_ports:
        if check_port_open('localhost', port):
            print(f"✅ Port {port}: OPEN")
        else:
            print(f"❌ Port {port}: CLOSED")
    
    # Check container ports
    containers = {
        'qemu-main-emulator-1': [5900, 5554, 5555],
        'qemu-main-emulator14-1': [5901, 6654, 5555]
    }
    
    for container, ports in containers.items():
        print(f"\n{container} port status:")
        for port in ports:
            try:
                result = subprocess.run(['docker', 'exec', container, 'netstat', '-ln'], 
                                      capture_output=True, text=True)
                if f":{port}" in result.stdout:
                    print(f"✅ Port {port}: LISTENING inside container")
                else:
                    print(f"❌ Port {port}: NOT LISTENING inside container")
            except Exception as e:
                print(f"❌ Port {port}: Error checking - {e}")

def check_port_open(host, port, timeout=2):
    """Check if a port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def test_api_endpoints():
    """Test API endpoints"""
    print("\n=== API ENDPOINTS TEST ===")
    
    base_url = "http://localhost:5001"
    
    # Test health
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        print(f"Health endpoint: {response.status_code}")
    except Exception as e:
        print(f"❌ Health endpoint failed: {e}")
        return
    
    # Test emulators list
    try:
        response = requests.get(f"{base_url}/api/emulators", timeout=5)
        print(f"Emulators endpoint: {response.status_code}")
        if response.status_code == 200:
            emulators = response.json()
            print(f"Found {len(emulators)} emulators")
            
            for emulator in emulators:
                emulator_id = emulator.get('id')
                print(f"\nTesting emulator {emulator_id}:")
                
                # Test VNC endpoint
                try:
                    vnc_response = requests.get(f"{base_url}/api/emulators/{emulator_id}/vnc", timeout=5)
                    print(f"VNC endpoint: {vnc_response.status_code}")
                    if vnc_response.status_code == 200:
                        print(json.dumps(vnc_response.json(), indent=2))
                except Exception as e:
                    print(f"VNC endpoint error: {e}")
                
                # Test screenshot
                try:
                    screenshot_response = requests.get(f"{base_url}/api/emulators/{emulator_id}/screenshot", timeout=10)
                    print(f"Screenshot endpoint: {screenshot_response.status_code}")
                except Exception as e:
                    print(f"Screenshot endpoint error: {e}")
                    
    except Exception as e:
        print(f"❌ Emulators endpoint failed: {e}")

def diagnose_vnc_setup():
    """Run comprehensive VNC diagnosis"""
    print("VNC DIAGNOSIS AND DEBUG REPORT")
    print("=" * 50)
    
    # Check if Docker is running
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ Docker is not running or accessible")
            return
        print("✅ Docker is running")
    except Exception as e:
        print(f"❌ Docker check failed: {e}")
        return
    
    check_docker_logs()
    check_vnc_ports()
    check_container_processes()
    test_api_endpoints()
    
    print("\n" + "=" * 50)
    print("DIAGNOSIS COMPLETE")
    print("=" * 50)

def fix_common_issues():
    """Try to fix common VNC issues"""
    print("\n=== ATTEMPTING COMMON FIXES ===")
    
    # Restart containers
    print("Restarting containers...")
    try:
        subprocess.run(['docker', 'compose', 'down'], check=True)
        time.sleep(2)
        subprocess.run(['docker', 'compose', 'up', '-d'], check=True)
        print("✅ Containers restarted")
        time.sleep(10)  # Wait for containers to start
    except Exception as e:
        print(f"❌ Failed to restart containers: {e}")
        return
    
    # Test after restart
    print("\nTesting after restart...")
    time.sleep(5)
    test_api_endpoints()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fix":
        fix_common_issues()
    else:
        diagnose_vnc_setup()
        print("\nTo attempt automatic fixes, run: python vnc_debug.py --fix") 