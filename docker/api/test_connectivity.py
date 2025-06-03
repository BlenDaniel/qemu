#!/usr/bin/env python3
"""
Connectivity test utility for API container to test access to other emulator containers
"""
import subprocess
import socket
import sys
import time

def test_port_connectivity(host, port, protocol="TCP"):
    """Test if a port is reachable"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"Error testing {host}:{port} - {e}")
        return False

def test_vnc_connection(host, port):
    """Test VNC connection to a host"""
    print(f"\n🔍 Testing VNC connection to {host}:{port}")
    
    # Test port connectivity
    if test_port_connectivity(host, port):
        print(f"✅ Port {port} is reachable on {host}")
        
        # Try to get VNC server info
        try:
            # Connect and read VNC protocol version
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, int(port)))
            
            # VNC servers send protocol version first
            version = sock.recv(12).decode()
            sock.close()
            
            if version.startswith("RFB"):
                print(f"✅ VNC server detected: {version.strip()}")
                return True
            else:
                print(f"❌ Non-VNC service on port {port}: {version}")
                return False
        except Exception as e:
            print(f"❌ VNC handshake failed: {e}")
            return False
    else:
        print(f"❌ Port {port} is not reachable on {host}")
        return False

def test_adb_connection(host, port):
    """Test ADB connection to a host"""
    print(f"\n🔍 Testing ADB connection to {host}:{port}")
    
    if test_port_connectivity(host, port):
        print(f"✅ Port {port} is reachable on {host}")
        
        # Try ADB connect
        try:
            cmd = ["adb", "connect", f"{host}:{port}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"✅ ADB connect successful: {result.stdout.strip()}")
                
                # Test ADB devices
                devices_result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
                print(f"📱 ADB devices: {devices_result.stdout}")
                return True
            else:
                print(f"❌ ADB connect failed: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ ADB command failed: {e}")
            return False
    else:
        print(f"❌ Port {port} is not reachable on {host}")
        return False

def main():
    """Main connectivity test"""
    print("🧪 Container-to-Container Connectivity Test")
    print("=" * 50)
    
    # Test configurations for docker-compose services
    test_configs = [
        {
            "name": "Android 11 Emulator",
            "service": "emulator",
            "vnc_port": 5900,  # Internal VNC port
            "adb_port": 5555,  # Internal ADB port
        },
        {
            "name": "Android 14 Emulator", 
            "service": "emulator14",
            "vnc_port": 5901,  # Internal VNC port
            "adb_port": 5555,  # Internal ADB port
        }
    ]
    
    all_tests_passed = True
    
    for config in test_configs:
        print(f"\n🧪 Testing {config['name']} ({config['service']})")
        print("-" * 40)
        
        # Test VNC
        vnc_ok = test_vnc_connection(config['service'], config['vnc_port'])
        
        # Test ADB  
        adb_ok = test_adb_connection(config['service'], config['adb_port'])
        
        if vnc_ok and adb_ok:
            print(f"✅ {config['name']}: All tests passed!")
        else:
            print(f"❌ {config['name']}: Some tests failed!")
            all_tests_passed = False
    
    print("\n" + "=" * 50)
    if all_tests_passed:
        print("🎉 All connectivity tests passed!")
        print("✅ API container can access other emulator containers via ADB and VNC")
    else:
        print("❌ Some connectivity tests failed")
        print("💡 Make sure all containers are running and emulators are started")
    
    return 0 if all_tests_passed else 1

if __name__ == "__main__":
    sys.exit(main()) 