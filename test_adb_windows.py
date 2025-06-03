#!/usr/bin/env python3
"""
Test script specifically for ADB connection improvements on Windows
"""

import requests
import time
import json
import subprocess
import socket
import platform
import os

API_BASE = "http://localhost:5001"

def test_adb_environment_setup():
    """Test ADB environment variable setup for Windows"""
    print("🔧 Testing ADB Environment Setup")
    print("Platform:", platform.system())
    
    # Test setting environment variable
    test_port = "8770"
    os.environ['ANDROID_ADB_SERVER_PORT'] = test_port
    
    if platform.system() == "Windows":
        try:
            # Test PowerShell environment variable setting
            ps_cmd = f'$env:ANDROID_ADB_SERVER_PORT = "{test_port}"'
            result = subprocess.run(['powershell', '-Command', ps_cmd], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("✅ PowerShell environment variable set successfully")
            else:
                print(f"❌ PowerShell environment variable failed: {result.stderr}")
        except Exception as e:
            print(f"❌ PowerShell test failed: {e}")
    
    # Test ADB command with environment
    try:
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
        print(f"✅ ADB devices command executed: {result.returncode == 0}")
        if result.stdout:
            print(f"  Output: {result.stdout.strip()}")
    except Exception as e:
        print(f"❌ ADB command failed: {e}")

def test_api_adb_functions():
    """Test the API's ADB connection functions"""
    print("\n🔧 Testing API ADB Functions")
    
    try:
        # Test container discovery
        response = requests.post(f"{API_BASE}/api/containers/discover", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Container Discovery: {data['message']}")
            
            # Test each discovered emulator
            for session_id in data.get('discovered_sessions', []):
                print(f"\nTesting session: {session_id}")
                
                # Test status endpoint
                status_response = requests.get(f"{API_BASE}/api/emulators/{session_id}/status", timeout=15)
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    adb_info = status_data.get('adb', {})
                    print(f"  ✅ Status check successful")
                    print(f"    Device found: {adb_info.get('device_found')}")
                    print(f"    Device status: {adb_info.get('device_status')}")
                    print(f"    Boot completed: {adb_info.get('boot_completed')}")
                    print(f"    Android version: {adb_info.get('android_version')}")
                else:
                    print(f"  ❌ Status check failed: {status_response.status_code}")
                
                # Test reconnect if device is not ready
                adb_info = status_data.get('adb', {}) if 'status_data' in locals() else {}
                if adb_info.get('device_status') != 'device':
                    print(f"  🔄 Attempting reconnection...")
                    reconnect_response = requests.post(f"{API_BASE}/api/emulators/{session_id}/reconnect", timeout=30)
                    if reconnect_response.status_code == 200:
                        reconnect_data = reconnect_response.json()
                        print(f"    ✅ Reconnect successful: {reconnect_data.get('connection_successful')}")
                        print(f"    Final status: {reconnect_data.get('final_device_status')}")
                    else:
                        print(f"    ❌ Reconnect failed: {reconnect_response.status_code}")
                
        else:
            print(f"❌ Container Discovery Failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ API test error: {e}")

def test_screenshot_after_connection():
    """Test screenshot functionality after establishing proper ADB connection"""
    print("\n📸 Testing Screenshot After ADB Connection")
    
    try:
        # Get list of emulators
        response = requests.get(f"{API_BASE}/api/emulators", timeout=10)
        if response.status_code == 200:
            emulators = response.json()
            
            for session_id, info in emulators.items():
                print(f"\nTesting screenshot for {session_id}")
                print(f"  Device ID: {info['device_id']}")
                print(f"  Status: {info['status']}")
                
                # Try screenshot
                screenshot_response = requests.get(f"{API_BASE}/api/emulators/{session_id}/screenshot", timeout=45)
                if screenshot_response.status_code == 200:
                    data = screenshot_response.json()
                    if data.get('success'):
                        print(f"  ✅ Screenshot captured successfully")
                        print(f"    Image size: {len(data['screenshot'])} characters")
                    else:
                        print(f"  ❌ Screenshot failed: {data.get('error')}")
                else:
                    print(f"  ❌ Screenshot request failed: {screenshot_response.status_code}")
                    
        else:
            print(f"❌ Failed to get emulators: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Screenshot test error: {e}")

def check_ports_accessibility():
    """Check if the expected ADB and VNC ports are accessible"""
    print("\n🔌 Checking Port Accessibility")
    
    ports_to_check = [
        ("5037", "ADB Server (Android 11)"),
        ("5555", "ADB Device (Android 11)"), 
        ("5901", "VNC (Android 11)"),
        ("6037", "ADB Server (Android 14)"),
        ("6655", "ADB Device (Android 14)"),
        ("5902", "VNC (Android 14)")
    ]
    
    for port, description in ports_to_check:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('localhost', int(port)))
            sock.close()
            
            if result == 0:
                print(f"  ✅ {description} (port {port}): Accessible")
            else:
                print(f"  ❌ {description} (port {port}): Not accessible")
        except Exception as e:
            print(f"  ❌ {description} (port {port}): Error - {e}")

def main():
    """Run comprehensive ADB connection tests"""
    print("🔧 Comprehensive ADB Connection Test Suite")
    print("=" * 60)
    
    # Test 1: Environment setup
    test_adb_environment_setup()
    
    # Test 2: Port accessibility 
    check_ports_accessibility()
    
    # Test 3: API ADB functions
    test_api_adb_functions()
    
    # Test 4: Screenshot functionality
    test_screenshot_after_connection()
    
    print("\n" + "=" * 60)
    print("🎉 ADB Connection Test Suite Complete!")
    print("\nIf you see connection issues:")
    print("1. Make sure Docker containers are running: docker ps")
    print("2. Check emulator logs: docker logs qemu-main-emulator-1")
    print("3. Restart containers: docker-compose down && docker-compose up -d")
    print("4. Wait 2-3 minutes for emulators to fully boot")

if __name__ == "__main__":
    main() 