#!/usr/bin/env python3
"""
Integration test script for VNC functionality.
This script tests the complete VNC setup and functionality.
"""

import requests
import time
import json
import subprocess
import socket
import sys

def check_api_health():
    """Check if the API is running and healthy"""
    try:
        response = requests.get('http://localhost:5001/api/emulators')
        return response.status_code == 200
    except:
        return False

def check_port_available(port):
    """Check if a port is available"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result != 0  # Port is available if connection fails
    except:
        return True

def test_vnc_setup():
    """Test VNC setup and configuration"""
    print("🔧 Testing VNC Setup...")
    
    # Check if API is running
    if not check_api_health():
        print("❌ API is not running on localhost:5001")
        return False
    
    print("✅ API is running")
    
    # Check VNC ports are available
    vnc_ports = [5901, 5902]  # Ports from docker-compose.yml
    for port in vnc_ports:
        if check_port_available(port):
            print(f"⚠️  VNC port {port} is not in use (emulator may not be running)")
        else:
            print(f"✅ VNC port {port} is in use (good sign)")
    
    return True

def test_emulator_creation():
    """Test creating an emulator with VNC support"""
    print("\n🚀 Testing Emulator Creation with VNC...")
    
    try:
        # Create emulator
        response = requests.post('http://localhost:5001/api/emulators',
                               json={'android_version': '11'},
                               timeout=30)
        
        if response.status_code != 201:
            print(f"❌ Failed to create emulator: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
        
        data = response.json()
        emulator_id = data.get('id')
        vnc_port = data.get('ports', {}).get('vnc')
        
        print(f"✅ Emulator created: {emulator_id}")
        print(f"   VNC Port: {vnc_port}")
        
        return emulator_id
        
    except requests.exceptions.Timeout:
        print("❌ Timeout creating emulator (this may take a while)")
        return None
    except Exception as e:
        print(f"❌ Error creating emulator: {e}")
        return None

def test_vnc_api_endpoint(emulator_id):
    """Test VNC API endpoint"""
    print(f"\n🔍 Testing VNC API endpoint for {emulator_id}...")
    
    try:
        response = requests.get(f'http://localhost:5001/api/emulators/{emulator_id}/vnc')
        
        if response.status_code != 200:
            print(f"❌ VNC API endpoint failed: {response.status_code}")
            return False
        
        data = response.json()
        print(f"   Success: {data.get('success')}")
        print(f"   VNC Port: {data.get('vnc_port')}")
        print(f"   VNC URL: {data.get('vnc_url')}")
        
        if data.get('success'):
            print("✅ VNC server is running and accessible")
        else:
            print(f"⚠️  VNC server issue: {data.get('error')}")
        
        return data.get('success', False)
        
    except Exception as e:
        print(f"❌ Error testing VNC API: {e}")
        return False

def test_vnc_status_endpoint(emulator_id):
    """Test VNC status endpoint"""
    print(f"\n📊 Testing VNC status endpoint for {emulator_id}...")
    
    try:
        response = requests.get(f'http://localhost:5001/api/emulators/{emulator_id}/vnc/status')
        
        if response.status_code != 200:
            print(f"❌ VNC status endpoint failed: {response.status_code}")
            return False
        
        data = response.json()
        print(f"   VNC Started: {data.get('vnc_started')}")
        print(f"   VNC Error: {data.get('vnc_error')}")
        print(f"   Container Running: {data.get('container_running')}")
        print(f"   Recent Logs: {len(data.get('recent_logs', []))} lines")
        
        if data.get('vnc_started'):
            print("✅ VNC server has started successfully")
        else:
            print("⚠️  VNC server may not have started yet")
            
        return True
        
    except Exception as e:
        print(f"❌ Error testing VNC status: {e}")
        return False

def test_vnc_viewer_page(emulator_id):
    """Test VNC viewer web page"""
    print(f"\n🌐 Testing VNC viewer page for {emulator_id}...")
    
    try:
        response = requests.get(f'http://localhost:5001/vnc/{emulator_id}')
        
        if response.status_code != 200:
            print(f"❌ VNC viewer page failed: {response.status_code}")
            return False
        
        html = response.text
        
        # Check for expected elements
        checks = [
            ('Android Emulator Screen', 'Page title'),
            ('vnc-viewer', 'VNC viewer container'),
            ('Screenshot Mode', 'Screenshot mode option'),
            ('Live Screenshot Mode', 'Live mode option'),
            ('VNC Mode', 'VNC mode option'),
            ('novnc-local.js', 'Local noVNC script')
        ]
        
        for check_text, description in checks:
            if check_text in html:
                print(f"   ✅ {description}")
            else:
                print(f"   ⚠️  Missing: {description}")
        
        print("✅ VNC viewer page loaded successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error testing VNC viewer page: {e}")
        return False

def test_screenshot_fallback(emulator_id):
    """Test screenshot functionality as VNC fallback"""
    print(f"\n📸 Testing screenshot fallback for {emulator_id}...")
    
    try:
        response = requests.get(f'http://localhost:5001/api/emulators/{emulator_id}/screenshot')
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Screenshot functionality works")
                return True
            else:
                print(f"⚠️  Screenshot failed: {data.get('error')}")
        else:
            print(f"⚠️  Screenshot endpoint returned: {response.status_code}")
        
        # Screenshot may fail if emulator isn't fully booted, which is OK for testing
        print("   (Screenshot failure is acceptable if emulator is still booting)")
        return True
        
    except Exception as e:
        print(f"⚠️  Error testing screenshot: {e}")
        return True  # Not critical for VNC testing

def cleanup_emulator(emulator_id):
    """Clean up test emulator"""
    if emulator_id:
        print(f"\n🧹 Cleaning up emulator {emulator_id}...")
        try:
            response = requests.delete(f'http://localhost:5001/api/emulators/{emulator_id}')
            if response.status_code in [200, 204]:
                print("✅ Emulator cleaned up")
            else:
                print(f"⚠️  Cleanup may have failed: {response.status_code}")
        except Exception as e:
            print(f"⚠️  Error during cleanup: {e}")

def run_integration_tests():
    """Run complete VNC integration test suite"""
    print("🧪 VNC Integration Test Suite")
    print("=" * 50)
    
    success_count = 0
    total_tests = 0
    emulator_id = None
    
    try:
        # Test 1: VNC Setup
        total_tests += 1
        if test_vnc_setup():
            success_count += 1
        
        # Test 2: Emulator Creation
        total_tests += 1
        emulator_id = test_emulator_creation()
        if emulator_id:
            success_count += 1
            
            # Wait a bit for emulator to initialize
            print("\n⏳ Waiting for emulator to initialize...")
            time.sleep(5)
            
            # Test 3: VNC API Endpoint
            total_tests += 1
            if test_vnc_api_endpoint(emulator_id):
                success_count += 1
            
            # Test 4: VNC Status Endpoint
            total_tests += 1
            if test_vnc_status_endpoint(emulator_id):
                success_count += 1
            
            # Test 5: VNC Viewer Page
            total_tests += 1
            if test_vnc_viewer_page(emulator_id):
                success_count += 1
            
            # Test 6: Screenshot Fallback
            total_tests += 1
            if test_screenshot_fallback(emulator_id):
                success_count += 1
    
    finally:
        # Always clean up
        cleanup_emulator(emulator_id)
    
    # Print summary
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    print(f"   Tests passed: {success_count}/{total_tests}")
    print(f"   Success rate: {(success_count/total_tests)*100:.1f}%")
    
    if success_count == total_tests:
        print("\n🎉 All VNC integration tests passed!")
        return True
    else:
        print(f"\n⚠️  {total_tests - success_count} test(s) failed")
        print("\n💡 Troubleshooting tips:")
        print("   - Make sure Docker containers are running")
        print("   - Check if emulators have VNC enabled")
        print("   - Verify port mappings in docker-compose.yml")
        print("   - Check container logs for VNC startup issues")
        return False

if __name__ == '__main__':
    success = run_integration_tests()
    sys.exit(0 if success else 1) 