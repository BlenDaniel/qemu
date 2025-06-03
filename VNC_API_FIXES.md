# VNC and API Connection Fixes

## Issues Identified and Fixed

### 1. **Container Startup Problem**
**Issue**: Emulator containers in `docker-compose.yml` were running `sleep infinity` instead of starting the Android emulator.

**Fix**: Modified `docker-compose.yml` to use the proper startup command:
```yaml
command: ["/usr/local/bin/start-emulator.sh"]
# command: ["sleep", "infinity"]  # Debug mode - commented out
```

### 2. **Port Mapping Issues**
**Issue**: The API was trying to connect to random ports (like 7305) that didn't match the container port mappings.

**Fix**: 
- Added proper ADB server port mapping (`5037:5037` and `6037:5037`)
- Defined clear port configurations in both docker-compose.yml and API code
- Added predefined container configurations for existing containers

### 3. **Session Management Mismatch**
**Issue**: The API only created new containers but couldn't discover or connect to existing docker-compose containers.

**Fix**: Added container discovery functionality:
- `discover_existing_containers()` function to find running containers
- Automatic registration of existing containers in sessions
- `setup_adb_for_existing_container()` for proper ADB connections
- New API endpoint `/api/containers/discover` for manual discovery

### 4. **VNC Configuration**
**Issue**: VNC was not properly set up for existing containers.

**Fix**: 
- Improved VNC port handling in the API
- Better VNC proxy setup for WebSocket connections
- Enhanced VNC status checking and error handling

## Changes Made

### 1. Modified `docker-compose.yml`
```yaml
services:
  emulator:
    ports:
      - "5901:5900"  # VNC access
      - "5554:5554"  # Emulator console
      - "5555:5555"  # ADB device port
      - "5037:5037"  # ADB server port
    command: ["/usr/local/bin/start-emulator.sh"]
    
  emulator14:
    ports:
      - "5902:5901"  # VNC access  
      - "6654:6654"  # Emulator console
      - "6655:5555"  # ADB device port
      - "6037:5037"  # ADB server port
    command: ["/usr/local/bin/start-emulator.sh"]
```

### 2. Enhanced `docker/api/app.py`
- Added `PREDEFINED_CONTAINERS` configuration
- Added `discover_existing_containers()` function
- Added `setup_adb_for_existing_container()` function
- Added `/api/containers/discover` endpoint
- Improved error handling and logging

### 3. Created `test_fixes.py`
Comprehensive test script to validate all fixes:
- API health checks
- Container discovery testing
- Emulator status validation
- VNC connectivity testing
- Screenshot functionality testing

## How to Use

### 1. Restart Containers
```bash
# Stop existing containers
docker-compose down

# Start with the fixed configuration
docker-compose up -d
```

### 2. Wait for Emulators to Boot
The emulators need time to start up properly (usually 2-3 minutes).

### 3. Discover Containers via API
```bash
# Trigger container discovery
curl -X POST http://localhost:5001/api/containers/discover

# List available emulators
curl http://localhost:5001/api/emulators
```

### 4. Test VNC Access
```bash
# Check VNC status for an emulator
curl http://localhost:5001/api/emulators/{emulator_id}/vnc

# Access VNC viewer in browser
http://localhost:5001/vnc/{emulator_id}
```

### 5. Run Comprehensive Tests
```bash
python test_fixes.py
```

## Expected Results

After applying these fixes, you should see:

1. **Container Discovery**: API finds existing containers automatically
2. **Proper Port Mapping**: 
   - Android 11 emulator: VNC on 5901, ADB on 5555, ADB server on 5037
   - Android 14 emulator: VNC on 5902, ADB on 6655, ADB server on 6037
3. **Working VNC**: Web-based VNC viewer accessible via browser
4. **ADB Connectivity**: Proper ADB connections for screenshots and device control
5. **Screenshot Functionality**: API can capture screenshots from emulators

## Troubleshooting

### If containers don't start:
1. Check Docker logs: `docker-compose logs emulator`
2. Ensure sufficient system resources (RAM, CPU)
3. Verify Android SDK images are properly installed

### If API can't discover containers:
1. Make sure containers are running: `docker ps`
2. Manually trigger discovery: `POST /api/containers/discover`
3. Check container names match the patterns in `PREDEFINED_CONTAINERS`

### If VNC doesn't work:
1. Check if VNC ports are accessible: `telnet localhost 5901`
2. Look at container logs for VNC startup messages
3. Ensure X11 and window manager are properly started in containers

### If ADB fails:
1. Check ADB server ports are mapped correctly
2. Wait for emulator to fully boot (check boot_completed property)
3. Try reconnecting: `POST /api/emulators/{id}/reconnect`

## Port Reference

| Service | Container Port | Host Port | Purpose |
|---------|---------------|-----------|---------|
| emulator (Android 11) | 5900 | 5901 | VNC Server |
| emulator (Android 11) | 5554 | 5554 | Emulator Console |
| emulator (Android 11) | 5555 | 5555 | ADB Device |
| emulator (Android 11) | 5037 | 5037 | ADB Server |
| emulator14 (Android 14) | 5901 | 5902 | VNC Server |
| emulator14 (Android 14) | 6654 | 6654 | Emulator Console |
| emulator14 (Android 14) | 5555 | 6655 | ADB Device |
| emulator14 (Android 14) | 5037 | 6037 | ADB Server |
| api | 5001 | 5001 | Flask API |
| api | 6080-6180 | 6080-6180 | VNC WebSocket Proxies |

## Next Steps

1. Restart your containers with the fixed configuration
2. Run the test script to validate everything works
3. Access the web interface at http://localhost:5001
4. Use VNC viewers at http://localhost:5001/vnc/{emulator_id}
5. Take screenshots via the API endpoints

The fixes should resolve all the connection issues between the API and emulator containers, enabling proper VNC access and screenshot functionality. 