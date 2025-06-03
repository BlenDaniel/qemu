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

def test_direct_emulator_adb(container_name):
    """Test direct connection to emulator's ADB server"""
    print(f"\n🔍 Testing direct emulator ADB connection to {container_name}")
    
    # Test ADB server port connectivity
    if test_port_connectivity(container_name, 5037):
        print(f"✅ ADB server port 5037 is reachable on {container_name}")
        
        # Try direct ADB connection
        try:
            cmd = ["adb", "-H", container_name, "-P", "5037", "devices"]
            print(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"✅ Direct ADB connection successful!")
                print(f"📱 Devices found:\n{result.stdout}")
                
                # Check if any emulator devices are listed
                lines = result.stdout.strip().split('\n')
                device_count = 0
                if len(lines) > 1:  # Skip header
                    for line in lines[1:]:
                        if line.strip() and "emulator-" in line:
                            device_count += 1
                            print(f"   📱 Found: {line.strip()}")
                
                if device_count > 0:
                    print(f"✅ Found {device_count} emulator device(s)")
                    return True
                else:
                    print(f"⚠️ ADB server connected but no emulator devices found")
                    return False
            else:
                print(f"❌ Direct ADB connection failed: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ ADB command failed: {e}")
            return False
    else:
        print(f"❌ ADB server port 5037 is not reachable on {container_name}")
        return False

def test_adb_connection(host, port):
    """Test ADB connection to a host (legacy method)"""
    print(f"\n🔍 Testing legacy ADB connection to {host}:{port}")
    
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

def test_dynamic_container(container_name):
    """Test connectivity to a dynamically created emulator container"""
    print(f"\n🧪 Testing Dynamic Container: {container_name}")
    print("-" * 50)
    
    # Test VNC port (5900 internal)
    vnc_ok = test_vnc_connection(container_name, 5900)
    
    # Test direct emulator ADB connection
    adb_ok = test_direct_emulator_adb(container_name)
    
    return vnc_ok and adb_ok

def main():
    """Main connectivity test"""
    print("🧪 Container-to-Container Connectivity Test")
    print("=" * 60)
    
    # Test configurations for docker-compose services
    predefined_configs = [
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
    
    # Test predefined containers
    for config in predefined_configs:
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
    
    # Test for dynamic containers by checking docker containers
    print(f"\n🔍 Looking for dynamic emulator containers...")
    try:
        # List docker containers to find dynamic emulators
        result = subprocess.run(["docker", "ps", "--format", "table {{.Names}}"], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            dynamic_containers = [line.strip() for line in lines if line.strip().startswith("emu_")]
            
            if dynamic_containers:
                print(f"Found {len(dynamic_containers)} dynamic emulator container(s)")
                for container_name in dynamic_containers:
                    container_ok = test_dynamic_container(container_name)
                    if not container_ok:
                        all_tests_passed = False
            else:
                print("No dynamic emulator containers found")
        else:
            print(f"Failed to list containers: {result.stderr}")
            
    except Exception as e:
        print(f"Error checking for dynamic containers: {e}")
    
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 All connectivity tests passed!")
        print("✅ API container can access other emulator containers via ADB and VNC")
    else:
        print("❌ Some connectivity tests failed")
        print("💡 Make sure all containers are running and emulators are started")
    
    print("\n🔧 Troubleshooting Tips:")
    print("- For dynamic containers: They use direct ADB server connection")
    print("- For predefined containers: They may be sleeping (docker-compose)")
    print("- Make sure emulators have finished booting")
    print("- Check container logs: docker logs <container_name>")
    
    return 0 if all_tests_passed else 1

if __name__ == "__main__":
    sys.exit(main()) 