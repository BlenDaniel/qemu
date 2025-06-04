#!/usr/bin/env python3
"""
Container Cleanup Script
Helps clean up orphaned Docker containers and free up ports
"""

import sys
import os
import logging
import docker
import time

# Add the docker/api directory to the Python path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'docker', 'api'))

from docker_manager import get_docker_client, cleanup_orphaned_containers, get_used_ports_from_containers

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def list_emulator_containers():
    """List all emulator-related containers"""
    try:
        docker_client = get_docker_client()
        if not docker_client:
            logger.error("Failed to connect to Docker daemon")
            return
        
        all_containers = docker_client.containers.list(all=True)
        emulator_containers = []
        
        for container in all_containers:
            if container.name.startswith('emu_') or 'emulator' in container.name.lower():
                emulator_containers.append(container)
        
        if not emulator_containers:
            logger.info("No emulator containers found")
            return
        
        logger.info(f"Found {len(emulator_containers)} emulator containers:")
        for container in emulator_containers:
            status = container.status
            ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
            port_info = []
            
            for container_port, host_bindings in ports.items():
                if host_bindings:
                    for binding in host_bindings:
                        if binding and 'HostPort' in binding:
                            port_info.append(f"{binding['HostPort']}:{container_port}")
            
            port_str = ', '.join(port_info) if port_info else 'No ports'
            logger.info(f"  - {container.name} [{status}] - Ports: {port_str}")
            
        return emulator_containers
        
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
        return []

def cleanup_all_emulator_containers():
    """Remove all emulator containers (both running and stopped)"""
    try:
        docker_client = get_docker_client()
        if not docker_client:
            logger.error("Failed to connect to Docker daemon")
            return False
        
        all_containers = docker_client.containers.list(all=True)
        removed_count = 0
        
        for container in all_containers:
            if container.name.startswith('emu_'):
                try:
                    logger.info(f"Removing container: {container.name}")
                    container.stop(timeout=10)
                    container.remove(force=True)
                    removed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to remove container {container.name}: {e}")
        
        logger.info(f"Removed {removed_count} emulator containers")
        return True
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return False

def show_port_usage():
    """Show current port usage by Docker containers"""
    try:
        used_ports = get_used_ports_from_containers()
        
        if not used_ports:
            logger.info("No ports currently in use by Docker containers")
            return
        
        logger.info(f"Ports currently in use by Docker containers:")
        sorted_ports = sorted(used_ports)
        
        # Group consecutive ports for better readability
        groups = []
        current_group = [sorted_ports[0]]
        
        for port in sorted_ports[1:]:
            if port == current_group[-1] + 1:
                current_group.append(port)
            else:
                groups.append(current_group)
                current_group = [port]
        groups.append(current_group)
        
        for group in groups:
            if len(group) == 1:
                logger.info(f"  - {group[0]}")
            else:
                logger.info(f"  - {group[0]}-{group[-1]} ({len(group)} ports)")
        
        # Highlight the docker-compose pre-allocated range
        api_range = set(range(6090, 6181))  # 6090-6180
        api_ports_in_use = api_range.intersection(used_ports)
        if api_ports_in_use:
            logger.info(f"\nNote: Ports {min(api_ports_in_use)}-{max(api_ports_in_use)} are pre-allocated by docker-compose API container")
            logger.info("This is normal and expected behavior.")
                
    except Exception as e:
        logger.error(f"Error checking port usage: {e}")

def main():
    """Main cleanup function"""
    logger.info("Docker Container Cleanup Tool")
    logger.info("=" * 40)
    
    while True:
        print("\nChoose an action:")
        print("1. List all emulator containers")
        print("2. Clean up orphaned containers only")
        print("3. Remove ALL emulator containers (dangerous!)")
        print("4. Show port usage")
        print("5. Show port allocation info")
        print("6. Exit")
        
        choice = input("\nEnter choice (1-6): ").strip()
        
        if choice == '1':
            logger.info("\nListing emulator containers...")
            list_emulator_containers()
            
        elif choice == '2':
            logger.info("\nCleaning up orphaned containers...")
            cleanup_orphaned_containers()
            
        elif choice == '3':
            confirm = input("\nThis will remove ALL emulator containers. Are you sure? (yes/no): ").strip().lower()
            if confirm == 'yes':
                logger.info("\nRemoving all emulator containers...")
                cleanup_all_emulator_containers()
            else:
                logger.info("Operation cancelled")
                
        elif choice == '4':
            logger.info("\nChecking port usage...")
            show_port_usage()
            
        elif choice == '5':
            logger.info("\nPort Allocation Information:")
            logger.info("=" * 30)
            logger.info("Port ranges used by the system:")
            logger.info("  Console ports:    5000-5999")
            logger.info("  ADB ports:        6000-6999")
            logger.info("  ADB server ports: 7000-7999")
            logger.info("  VNC ports:        5900-5950")
            logger.info("  Websockify ports: 6200-6300")
            logger.info("")
            logger.info("Pre-allocated by docker-compose:")
            logger.info("  API container:    6090-6180 (91 ports)")
            logger.info("")
            logger.info("Note: The system automatically avoids conflicts between")
            logger.info("these ranges and the pre-allocated docker-compose ports.")
            
        elif choice == '6':
            logger.info("Exiting...")
            break
            
        else:
            print("Invalid choice. Please enter 1-6.")

if __name__ == "__main__":
    main() 