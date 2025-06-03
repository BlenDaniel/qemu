#!/usr/bin/env python3
"""
Test script to validate container discovery and ADB connection fixes
"""

import requests
import time
import json

API_BASE = "http://localhost:5001"

def test_container_discovery():
    """Test the container discovery functionality"""
    print("🔍 Testing Container Discovery")
    print("=" * 50)
    
    try:
        # Test manual discovery trigger
        print("1. Triggering container discovery...")
        response = requests.post(f"{API_BASE}/api/containers/discover", timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Discovery successful: {data['message']}")
            print(f"   Sessions discovered: {data.get('discovered_sessions', [])}")
            
            if not data.get('discovered_sessions'):
                print("⚠️  No sessions discovered - this might indicate container name mismatch")
                return False
            
            return True
        else:
            print(f"❌ Discovery failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Discovery error: {e}")
        return False

def test_emulator_listing():
    """Test listing emulators after discovery"""
    print("\n2. Testing emulator listing...")
    
    try:
        response = requests.get(f"{API_BASE}/api/emulators", timeout=10)
        if response.status_code == 200:
            emulators = response.json()
            print(f"✅ Found {len(emulators)} emulator(s)")
            
            for session_id, info in emulators.items():
                print(f"\n📱 Emulator: {session_id}")
                print(f"   Device ID: {info['device_id']}")
                print(f"   Android: {info['android_version']}")
                print(f"   Container: {info.get('container_name', 'unknown')}")
                print(f"   Status: {info['status']}")
                print(f"   Is Predefined: {info.get('is_predefined', False)}")
                print(f"   Ports: {info['ports']}")
                
                # Check if it's a predefined container
                if info.get('is_predefined'):
                    print("   ✅ This is a docker-compose container")
                else:
                    print("   ⚠️  This is a dynamically created container")
                    
            return emulators
        else:
            print(f"❌ Failed to list emulators: {response.status_code}")
            return {}
            
    except Exception as e:
        print(f"❌ Error listing emulators: {e}")
        return {}

def test_emulator_status(session_id, emulator_info):
    """Test individual emulator status"""
    print(f"\n3. Testing status for {session_id}...")
    
    try:
        response = requests.get(f"{API_BASE}/api/emulators/{session_id}/status", timeout=15)
        if response.status_code == 200:
            data = response.json()
            adb_info = data.get('adb', {})
            
            print(f"   Container Status: {data.get('container_status')}")
            print(f"   ADB Device Found: {adb_info.get('device_found')}")
            print(f"   ADB Device Status: {adb_info.get('device_status')}")
            print(f"   Boot Completed: {adb_info.get('boot_completed')}")
            print(f"   Android Version: {adb_info.get('android_version')}")
            
            return adb_info.get('device_status')
        else:
            print(f"   ❌ Status check failed: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"   ❌ Status check error: {e}")
        return None

def test_reconnection(session_id):
    """Test ADB reconnection for an emulator"""
    print(f"\n4. Testing ADB reconnection for {session_id}...")
    
    try:
        response = requests.post(f"{API_BASE}/api/emulators/{session_id}/reconnect", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Reconnection completed")
            print(f"   Connection Successful: {data.get('connection_successful')}")
            print(f"   Final Device Status: {data.get('final_device_status')}")
            return data.get('connection_successful')
        else:
            print(f"   ❌ Reconnection failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Reconnection error: {e}")
        return False

def test_api_health():
    """Test API health and Docker connection"""
    print("🏥 Testing API Health")
    print("-" * 30)
    
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API Status: {data['status']}")
            print(f"✅ Docker: {data['docker']}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        return False

def main():
    """Run comprehensive container discovery tests"""
    print("🔧 Container Discovery & Connection Test Suite")
    print("=" * 60)
    
    # Test API health first
    if not test_api_health():
        print("\n❌ API is not healthy. Cannot continue tests.")
        return
    
    # Test container discovery
    if not test_container_discovery():
        print("\n❌ Container discovery failed. Check container names and patterns.")
        return
    
    # Test emulator listing
    emulators = test_emulator_listing()
    if not emulators:
        print("\n❌ No emulators found after discovery.")
        return
    
    # Test each emulator
    for session_id, info in emulators.items():
        print(f"\n🧪 Testing Emulator: {session_id}")
        print("-" * 40)
        
        # Test status
        device_status = test_emulator_status(session_id, info)
        
        # If device is not ready, try reconnection
        if device_status != 'device':
            print(f"   Device status is '{device_status}', attempting reconnection...")
            reconnection_success = test_reconnection(session_id)
            
            if reconnection_success:
                print("   ✅ Reconnection successful")
            else:
                print("   ❌ Reconnection failed")
    
    print("\n" + "=" * 60)
    print("🎉 Container Discovery Test Suite Complete!")
    print("\nNext steps if issues persist:")
    print("1. Check container names: docker ps")
    print("2. Check emulator logs: docker logs <container_name>")
    print("3. Wait for emulators to fully boot (2-3 minutes)")
    print("4. Try manual reconnection via API")

if __name__ == "__main__":
    main() 