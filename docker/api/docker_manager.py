import docker
import logging
import uuid
import random
import time
import os

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
            "vnc": "5901",  # Host port for VNC
            "websockify": "6081"  # Host port for websockify
        },
        "internal_ports": {
            "console": "5554",
            "adb": "5555",
            "adb_server": "5037", 
            "vnc": "5900",  # Internal container port for VNC
            "websockify": "6080"  # Internal container port for websockify
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
            "vnc": "5902",  # Host port for VNC
            "websockify": "6082"  # Host port for websockify
        },
        "internal_ports": {
            "console": "6654",
            "adb": "5555",  # Internal container port
            "adb_server": "5037",
            "vnc": "5901",  # Internal container port for VNC
            "websockify": "6080"  # Internal container port for websockify
        }
    }
}

# Make Docker client initialization lazy for testing
client = None

def get_docker_client():
    global client
    if client is None:
        try:
            # Clear any problematic Docker environment variables that might cause "http+docker" scheme errors
            original_docker_host = os.environ.get('DOCKER_HOST', None)
            if original_docker_host and 'http+docker' in original_docker_host:
                logger.warning(f"Clearing malformed DOCKER_HOST: {original_docker_host}")
                del os.environ['DOCKER_HOST']
            
            # First try the default method (from environment)
            client = docker.from_env()
            # Test the connection
            client.ping()
            logger.info("Docker client connected successfully via environment")
            return client
        except Exception as e:
            logger.warning(f"Default Docker connection failed: {e}")
            
            # Clear any Docker-related env vars that might be interfering
            docker_env_vars = ['DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH']
            cleared_vars = []
            for var in docker_env_vars:
                if var in os.environ:
                    cleared_vars.append(f"{var}={os.environ[var]}")
                    del os.environ[var]
            
            if cleared_vars:
                logger.info(f"Cleared Docker environment variables: {cleared_vars}")
            
            try:
                # Try explicit Unix socket connection
                client = docker.DockerClient(base_url='unix://var/run/docker.sock')
                client.ping()
                logger.info("Docker client connected via Unix socket")
                return client
            except Exception as e2:
                logger.warning(f"Unix socket connection failed: {e2}")
                try:
                    # Try Docker Desktop default socket on macOS/Windows
                    client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
                    client.ping()
                    logger.info("Docker client connected via Docker Desktop socket")
                    return client
                except Exception as e3:
                    logger.warning(f"Docker Desktop socket failed: {e3}")
                    try:
                        # Try TCP connection (for Docker daemon with TCP enabled)
                        client = docker.DockerClient(base_url='tcp://localhost:2375')  # Note: 2375, not 2376
                        client.ping()
                        logger.info("Docker client connected via TCP (localhost:2375)")
                        return client
                    except Exception as e4:
                        logger.warning(f"TCP connection (2375) failed: {e4}")
                        try:
                            # Try secure TCP connection
                            client = docker.DockerClient(base_url='tcp://localhost:2376')
                            client.ping()
                            logger.info("Docker client connected via secure TCP (localhost:2376)")
                            return client
                        except Exception as e5:
                            logger.error(f"All Docker connection methods failed. Last error: {e5}")
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
                        'websockify_port': config['ports']['websockify'],
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
        error_msg = "Docker daemon is not accessible. Please check if Docker is running and the API container has proper permissions."
        logger.error(error_msg)
        raise Exception(error_msg)
    
    emulator_image = EMULATOR_IMAGES.get(android_version, EMULATOR_IMAGES["11"])
    container_name = f"emu_{device_id}_{session_id[:8]}"
    
    logger.info(f"Creating emulator container: {container_name}")
    logger.info(f"Image: {emulator_image}")
    logger.info(f"Port bindings: {port_bindings}")
    logger.info(f"Environment: {environment}")
    
    try:
        # Run container with specified port bindings
        container = docker_client.containers.run(
            emulator_image,
            detach=True,
            privileged=True,
            environment=environment,
            name=container_name,
            ports=port_bindings,
            remove=False  # Don't auto-remove container
        )
        logger.info(f"✅ Successfully created container: {container_name} (ID: {container.id[:12]})")
        return container
    except docker.errors.ImageNotFound:
        error_msg = f"Emulator image {emulator_image} not found. Build the image first."
        logger.error(error_msg)
        raise Exception(error_msg)
    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        raise Exception(f"Docker API error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to create emulator container {container_name}: {e}")
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
        'vnc_port': random.randint(5900, 6000),
        'websockify_port': random.randint(6090, 6200)
    }

def get_container_port_mappings(container):
    """Get port mappings from a container"""
    try:
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        return {
            'console': ports.get('5554/tcp', [{}])[0].get('HostPort', 'unknown'),
            'adb': ports.get('5555/tcp', [{}])[0].get('HostPort', 'unknown'),
            'adb_server': ports.get('5037/tcp', [{}])[0].get('HostPort', 'unknown'),
            'vnc': ports.get('5900/tcp', [{}])[0].get('HostPort', 'unknown'),
            'websockify': ports.get('6080/tcp', [{}])[0].get('HostPort', 'unknown')
        }
    except Exception as e:
        logger.error(f"Error getting container port mappings: {e}")
        return {
            'console': 'unknown',
            'adb': 'unknown',
            'adb_server': 'unknown',
            'vnc': 'unknown',
            'websockify': 'unknown'
        }

def wait_for_container_ports(container, timeout=60):
    """Wait for container to bind its ports"""
    logger.info(f"Waiting for container {container.name} to bind ports...")
    for i in range(timeout):
        try:
            container.reload()
            ports = container.attrs['NetworkSettings']['Ports']
            if ports and ports.get('5555/tcp'):
                logger.info(f"Container {container.name} ports are ready after {i+1} seconds")
                return True
        except Exception as e:
            logger.warning(f"Error checking container ports (attempt {i+1}): {e}")
        time.sleep(1)
    
    logger.warning(f"Container {container.name} ports not ready after {timeout} seconds")
    return False

def check_docker_connectivity():
    """Check if Docker is accessible and return status info"""
    docker_client = get_docker_client()
    if not docker_client:
        return {
            'connected': False,
            'error': 'Docker client could not be initialized'
        }
    
    try:
        info = docker_client.info()
        return {
            'connected': True,
            'version': docker_client.version(),
            'containers_running': info.get('ContainersRunning', 0),
            'images': len(docker_client.images.list())
        }
    except Exception as e:
        return {
            'connected': False,
            'error': str(e)
        } 