#!/usr/bin/env python3
"""
Test script to validate the emulator API fixes
"""

import requests
import time
import json
import subprocess
import socket

API_BASE = "http://localhost:5001"

def test_connection(host, port, timeout=5):
    """Test if a port is accessible"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0
    except:
        return False

def check_api_health():
    """Check if API is running and healthy"""
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API Health: {data['status']}")
            print(f"  Docker: {data['docker']}")
            return True
        else:
            print(f"❌ API Health Check Failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        return False

def discover_containers():
    """Trigger container discovery"""
    try:
        response = requests.post(f"{API_BASE}/api/containers/discover", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Container Discovery: {data['message']}")
            print(f"  Sessions discovered: {data['discovered_sessions']}")
            return data['discovered_sessions']
        else:
            print(f"❌ Container Discovery Failed: {response.status_code}")
            if response.text:
                print(f"  Error: {response.text}")
            return []
    except Exception as e:
        print(f"❌ Container Discovery Error: {e}")
        return []

def list_emulators():
    """List all available emulators"""
    try:
        response = requests.get(f"{API_BASE}/api/emulators", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {len(data)} emulator(s)")
            for session_id, info in data.items():
                print(f"  - {session_id}:")
                print(f"    Device ID: {info['device_id']}")
                print(f"    Android: {info['android_version']}")
                print(f"    Status: {info['status']}")
                print(f"    Ports: {info['ports']}")
            return data
        else:
            print(f"❌ Failed to list emulators: {response.status_code}")
            return {}
    except Exception as e:
        print(f"❌ Error listing emulators: {e}")
        return {}

def test_emulator_status(session_id):
    """Test emulator status and connectivity"""
    try:
        response = requests.get(f"{API_BASE}/api/emulators/{session_id}/status", timeout=15)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Emulator {session_id} Status:")
            print(f"  Container: {data['container_status']}")
            print(f"  ADB Device: {data['adb']['device_found']} ({data['adb']['device_status']})")
            print(f"  Boot Complete: {data['adb']['boot_completed']}")
            print(f"  Android Version: {data['adb']['android_version']}")
            return data
        else:
            print(f"❌ Status check failed for {session_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error checking status for {session_id}: {e}")
        return None

def test_vnc_connectivity(session_id, emulators_data):
    """Test VNC connectivity for an emulator"""
    if session_id not in emulators_data:
        print(f"❌ Session {session_id} not found in emulators data")
        return False
    
    vnc_port = emulators_data[session_id]['ports'].get('vnc')
    if not vnc_port or vnc_port == 'unknown':
        print(f"❌ No VNC port configured for {session_id}")
        return False
    
    # Test VNC port connectivity
    if test_connection('localhost', vnc_port):
        print(f"✅ VNC port {vnc_port} is accessible for {session_id}")
        
        # Test VNC proxy endpoint
        try:
            response = requests.get(f"{API_BASE}/api/emulators/{session_id}/vnc", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ VNC proxy setup successful:")
                print(f"  VNC Port: {data['vnc_port']}")
                print(f"  Proxy Port: {data.get('proxy_port', 'N/A')}")
                print(f"  WebSocket URL: {data.get('ws_url', 'N/A')}")
                return True
            else:
                print(f"❌ VNC proxy setup failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ VNC proxy test error: {e}")
            return False
    else:
        print(f"❌ VNC port {vnc_port} is not accessible for {session_id}")
        return False

def test_screenshot(session_id):
    """Test screenshot functionality"""
    try:
        print(f"📸 Testing screenshot for {session_id}...")
        response = requests.get(f"{API_BASE}/api/emulators/{session_id}/screenshot", timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ Screenshot captured successfully for {session_id}")
                print(f"  Image size: {len(data['screenshot'])} characters (base64)")
                return True
            else:
                print(f"❌ Screenshot failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ Screenshot request failed: {response.status_code}")
            if response.text:
                try:
                    error_data = response.json()
                    print(f"  Error: {error_data.get('error', response.text)}")
                except:
                    print(f"  Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Screenshot test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🔧 Testing Android Emulator API Fixes")
    print("=" * 50)
    
    # Test 1: API Health
    print("\n1. Testing API Health...")
    if not check_api_health():
        print("❌ API is not healthy. Cannot continue tests.")
        return
    
    # Test 2: Container Discovery
    print("\n2. Testing Container Discovery...")
    sessions = discover_containers()
    
    # Test 3: List Emulators
    print("\n3. Testing Emulator Listing...")
    emulators = list_emulators()
    
    if not emulators:
        print("❌ No emulators found. Make sure containers are running.")
        return
    
    # Test each emulator
    for session_id in emulators.keys():
        print(f"\n4. Testing Emulator: {session_id}")
        print("-" * 30)
        
        # Test status
        status = test_emulator_status(session_id)
        
        # Test VNC
        test_vnc_connectivity(session_id, emulators)
        
        # Test screenshot (only if device is ready)
        if status and status.get('adb', {}).get('device_status') == 'device':
            test_screenshot(session_id)
        else:
            print(f"⏭️  Skipping screenshot test - device not ready")
    
    print("\n" + "=" * 50)
    print("🎉 Test Suite Complete!")

if __name__ == "__main__":
    main() 