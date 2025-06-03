import docker
import logging
import uuid
import random
import time

logger = logging.getLogger(__name__)

# Emulator image configurations
EMULATOR_IMAGES = {
    "11": "qemu-emulator",           # Android 11 image
    "14": "qemu-emulator-android14"  # Android 14 image
}

# Predefined container configurations for docker-compose containers
PREDEFINED_CONTAINERS = {
    "emulator": {
        "container_name_pattern": "qemu-emulator-1",  # Fixed: actual container name
        "container_host": "emulator",  # Docker service name for networking
        "android_version": "11",
        "device_id": "android11_main",
        "ports": {
            "console": "5554",
            "adb": "5555", 
            "adb_server": "5037",
            "vnc": "5901"  # Host port for VNC
        },
        "internal_ports": {
            "console": "5554",
            "adb": "5555",
            "adb_server": "5037", 
            "vnc": "5900"  # Internal container port for VNC
        }
    },
    "emulator14": {
        "container_name_pattern": "qemu-emulator14-1",  # Fixed: actual container name
        "container_host": "emulator14",  # Docker service name for networking
        "android_version": "14",
        "device_id": "android14_main",
        "ports": {
            "console": "6654",
            "adb": "6655",
            "adb_server": "6037", 
            "vnc": "5902"  # Host port for VNC
        },
        "internal_ports": {
            "console": "6654",
            "adb": "5555",  # Internal container port
            "adb_server": "5037",
            "vnc": "5901"  # Internal container port for VNC
        }
    }
}

# Make Docker client initialization lazy for testing
client = None

def get_docker_client():
    global client
    if client is None:
        try:
            # Try different connection methods
            # First try the default method
            client = docker.from_env()
            # Test the connection
            client.ping()
            logger.info("Docker client connected successfully")
        except Exception as e:
            logger.warning(f"Default Docker connection failed: {e}")
            try:
                # Try explicit Unix socket connection
                client = docker.DockerClient(base_url='unix://var/run/docker.sock')
                client.ping()
                logger.info("Docker client connected via Unix socket")
            except Exception as e2:
                logger.warning(f"Unix socket connection failed: {e2}")
                try:
                    # Try TCP connection
                    client = docker.DockerClient(base_url='tcp://localhost:2376')
                    client.ping()
                    logger.info("Docker client connected via TCP")
                except Exception as e3:
                    logger.error(f"All Docker connection methods failed: {e3}")
                    # Set client to None so we can provide better error messages
                    client = None
    return client

def discover_existing_containers(sessions):
    """Discover and register existing emulator containers on startup"""
    docker_client = get_docker_client()
    if not docker_client:
        logger.warning("Cannot discover containers - Docker client not available")
        return
    
    try:
        # Get all running containers
        containers = docker_client.containers.list()
        logger.info(f"Found {len(containers)} running containers")
        
        for container in containers:
            container_name = container.name
            logger.info(f"Checking container: {container_name}")
            
            # Skip containers that are just sleeping (dormant prototypes)
            container_info = container.attrs
            command = container_info.get('Config', {}).get('Cmd', [])
            if command and len(command) >= 2 and command[0] == "sleep" and command[1] == "infinity":
                logger.info(f"Skipping dormant prototype container: {container_name} (sleeping)")
                continue
            
            # Check if this is one of our predefined emulator containers
            for service_name, config in PREDEFINED_CONTAINERS.items():
                pattern = config["container_name_pattern"]
                # Check for exact match or partial match (for docker-compose prefixes)
                if pattern in container_name or container_name.endswith(pattern):
                    # Generate session ID for this container
                    session_id = f"existing_{service_name}_{config['device_id']}"
                    
                    # Skip if already registered
                    if session_id in sessions:
                        logger.info(f"Container {container_name} already registered as {session_id}")
                        continue
                    
                    # Register container in sessions
                    sessions[session_id] = {
                        'container': container,
                        'device_port': config['ports']['console'],
                        'ports': config['ports'],
                        'device_id': config['device_id'],
                        'android_version': config['android_version'],
                        'has_external_adb_server': True,
                        'vnc_port': config['ports']['vnc'],
                        'is_predefined': True
                    }
                    
                    logger.info(f"✅ Registered existing container {container_name} as session {session_id}")
                    logger.info(f"   Ports: {config['ports']}")
                    
                    # Try to set up ADB connection
                    try:
                        from adb_manager import setup_adb_for_existing_container
                        adb_success = setup_adb_for_existing_container(session_id, config)
                        logger.info(f"   ADB setup: {'✅ Success' if adb_success else '❌ Failed'}")
                    except ImportError as e:
                        logger.warning(f"Could not import ADB manager: {e}")
                    break
                    
    except Exception as e:
        logger.error(f"Error discovering existing containers: {e}")

def create_emulator_container(android_version, device_id, session_id, port_bindings, environment):
    """Create a new emulator container"""
    docker_client = get_docker_client()
    if docker_client is None:
        raise Exception("Docker daemon is not accessible. Please check if Docker is running and the API container has proper permissions.")
    
    emulator_image = EMULATOR_IMAGES.get(android_version, EMULATOR_IMAGES["11"])
    
    try:
        # Run container with specified port bindings
        container = docker_client.containers.run(
            emulator_image,
            detach=True,
            privileged=True,
            environment=environment,
            name=f"emu_{device_id}_{session_id[:8]}",
            ports=port_bindings
        )
        return container
    except docker.errors.ImageNotFound:
        raise Exception(f"Emulator image {emulator_image} not found. Build the image first.")
    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        raise Exception(f"Docker API error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to create emulator: {e}")
        raise Exception(f"Failed to create emulator: {str(e)}")

def generate_device_id():
    """Generate a unique device ID for the emulator"""
    import string
    letters_and_digits = string.ascii_lowercase + string.digits
    device_id = ''.join(random.choice(letters_and_digits) for _ in range(8))
    return device_id

def generate_random_ports():
    """Generate random ports for emulator services"""
    return {
        'console_port': random.randint(5000, 9999),
        'adb_port': random.randint(5000, 9999), 
        'internal_adb_server_port': random.randint(5000, 9999),
        'vnc_port': random.randint(5900, 6000)
    }

def get_container_port_mappings(container):
    """Get port mappings from a container"""
    container.reload()
    ports = container.attrs['NetworkSettings']['Ports']
    return {
        'console': ports.get('5554/tcp', [{}])[0].get('HostPort', 'unknown'),
        'adb': ports.get('5555/tcp', [{}])[0].get('HostPort', 'unknown'),
        'adb_server': ports.get('5037/tcp', [{}])[0].get('HostPort', 'unknown'),
        'vnc': ports.get('5900/tcp', [{}])[0].get('HostPort', 'unknown')
    }

def wait_for_container_ports(container, timeout=60):
    """Wait for container to bind its ports"""
    for _ in range(timeout):
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        if ports and ports.get('5555/tcp'):
            return True
        time.sleep(1)
    return False 