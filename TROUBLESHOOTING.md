# Docker Emulator Port Conflict Troubleshooting Guide

This guide addresses common port allocation issues that can occur when running multiple Android emulator containers.

## Common Issues and Solutions

### Port Already Allocated Errors

**Problem**: You see errors like:
```
Docker API error: 500 Server Error for http+docker://localhost/v1.47/containers/.../start: 
Internal Server Error ("driver failed programming external connectivity on endpoint ... 
Bind for 0.0.0.0:6118 failed: port is already allocated")
```

**Root Causes**:
1. Previous containers that didn't shut down cleanly are still holding ports
2. Multiple containers trying to use the same port range
3. Host system services using the same ports

**Solutions**:

#### 1. Automatic Port Conflict Resolution (Built-in)
The system now includes automatic port conflict resolution:
- Automatically detects used ports before allocation
- Retries with different ports if conflicts occur
- Cleans up orphaned containers automatically

#### 2. Manual Container Cleanup
Use the cleanup script to manually resolve issues:
```bash
python3 scripts/cleanup_containers.py
```

Options available:
- List all emulator containers and their port usage
- Clean up orphaned containers only (safe)
- Remove all emulator containers (use with caution)
- Show current port usage

#### 3. Docker System Cleanup
For severe cases, clean up the entire Docker system:
```bash
# Stop all containers
docker stop $(docker ps -q)

# Remove all stopped containers
docker container prune -f

# Remove all unused networks
docker network prune -f

# Restart Docker (on macOS/Windows)
# Or restart Docker service on Linux
```

#### 4. Check System Port Usage
Identify what's using specific ports:
```bash
# macOS/Linux
lsof -i :6118
netstat -an | grep :6118

# Windows
netstat -an | findstr :6118
```

### ADB Connection Issues

**Problem**: Emulators start but ADB can't connect

**Solutions**:
1. Use the API reconnection endpoint:
   ```bash
   curl -X POST http://localhost:5001/api/emulators/<emulator_id>/reconnect
   ```

2. Restart ADB server manually:
   ```bash
   adb kill-server
   adb start-server
   ```

3. Check if ports are properly mapped:
   ```bash
   docker port <container_name>
   ```

### Performance and Resource Issues

**Problem**: System becomes slow or unresponsive with multiple emulators

**Solutions**:
1. Limit concurrent emulators based on system resources
2. Use the cleanup script to remove unused containers
3. Monitor system resources:
   ```bash
   docker stats
   htop  # or top on macOS
   ```

## Prevention Best Practices

### 1. Graceful Shutdown
Always stop containers properly:
```bash
# Via API
curl -X DELETE http://localhost:5001/api/emulators/<session_id>

# Via Docker
docker stop <container_name>
docker rm <container_name>
```

### 2. Regular Cleanup
Run cleanup scripts periodically:
```bash
# Weekly cleanup of orphaned containers
python3 scripts/cleanup_containers.py
```

### 3. Monitor Port Usage
Check port allocation before creating new emulators:
```bash
# Check Docker port usage
docker ps --format "table {{.Names}}\t{{.Ports}}"

# Check system port usage
netstat -tlnp | grep :6
```

### 4. Use Docker Compose for Consistent Environments
For development, use the predefined containers in docker-compose.yml:
```bash
docker-compose up -d
```

## Advanced Troubleshooting

### Port Range Configuration
Modify port ranges in `docker/api/docker_manager.py`:
```python
port_ranges = {
    'console_port': (5000, 5999),
    'adb_port': (6000, 6999), 
    'internal_adb_server_port': (7000, 7999),
    'vnc_port': (5900, 5950),
    'websockify_port': (6200, 6300)  # Avoid 6090-6180 (docker-compose range)
}
```

### Enable Debug Logging
Add debug logging to see detailed port allocation:
```python
# In docker/api/app.py
logging.basicConfig(level=logging.DEBUG)
```

### Container Networking Issues
If containers can't communicate:
```bash
# Check Docker networks
docker network ls
docker network inspect qemu_default

# Recreate network if needed
docker-compose down
docker network prune -f
docker-compose up -d
```

## Recovery Procedures

### Complete System Reset
If all else fails, perform a complete reset:

1. Stop all services:
   ```bash
   docker-compose down
   ```

2. Clean up everything:
   ```bash
   python3 scripts/cleanup_containers.py  # Choose option 3
   docker system prune -a -f
   ```

3. Restart services:
   ```bash
   docker-compose up -d
   ```

### Backup and Restore
Before major changes, backup your configuration:
```bash
# Backup container data
cp -r avd-data avd-data.backup

# Backup Docker compose configuration
cp docker-compose.yml docker-compose.yml.backup
```

## Monitoring and Alerting

### Log Monitoring
Watch for port conflicts in logs:
```bash
# API logs
tail -f docker/api/logs/app.log

# Docker compose logs
docker-compose logs -f api
```

### Health Checks
Implement health checks to detect issues early:
```bash
# Check API health
curl http://localhost:5001/api/emulators

# Check container health
docker ps --filter "name=emu_"
```

## Contact and Support

If issues persist after following this guide:
1. Check the GitHub issues for similar problems
2. Collect logs using: `docker-compose logs > debug.log`
3. Include system information: OS, Docker version, available RAM/CPU
4. Provide the output of `python3 scripts/cleanup_containers.py` (option 1) 