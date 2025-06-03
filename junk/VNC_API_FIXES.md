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

### 5. **ADB Connection Reliability (NEW)**
**Issue**: ADB connections were unreliable, especially on Windows machines, with poor error handling and retry logic.

**Fix**: Implemented robust ADB connection system:
- **Cross-platform environment variable handling**: Proper PowerShell support for Windows (`$env:ANDROID_ADB_SERVER_PORT`)
- **Robust server restart**: `robust_adb_server_restart()` with proper cleanup
- **Smart device detection**: `detect_device_with_retry()` with configurable retries
- **Better error handling**: Detailed logging and timeout management
- **Process cleanup**: Improved killing of stray ADB processes

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

### 2. Enhanced `docker/api/app.py` (NEW IMPROVEMENTS)
- **NEW**: `robust_adb_server_restart()` - Complete ADB server restart with cleanup
- **NEW**: `detect_device_with_retry()` - Intelligent device detection with retries
- **IMPROVED**: `set_adb_environment()` - Windows PowerShell support
- **IMPROVED**: `run_adb_command()` - Better timeout and error handling
- **IMPROVED**: `kill_all_adb_processes()` - Cross-platform process cleanup
- **UPDATED**: All endpoints now use robust ADB functions

### 3. New Test Scripts
- **Enhanced**: `test_fixes.py` - Comprehensive validation
- **NEW**: `test_adb_windows.py` - Windows-specific ADB testing

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

### 4. Test ADB Connections (NEW)
```bash
# Run comprehensive ADB tests
python test_adb_windows.py

# Test basic functionality
python test_fixes.py
```

### 5. Test VNC Access
```bash
# Check VNC status for an emulator
curl http://localhost:5001/api/emulators/{emulator_id}/vnc

# Access VNC viewer in browser
http://localhost:5001/vnc/{emulator_id}
```

### 6. Force Reconnection if Needed
```bash
# Reconnect to an emulator with robust ADB restart
curl -X POST http://localhost:5001/api/emulators/{emulator_id}/reconnect
```

## Expected Results

After applying these fixes, you should see:

1. **Container Discovery**: API finds existing containers automatically
2. **Proper Port Mapping**: 
   - Android 11 emulator: VNC on 5901, ADB on 5555, ADB server on 5037
   - Android 14 emulator: VNC on 5902, ADB on 6655, ADB server on 6037
3. **Working VNC**: Web-based VNC viewer accessible via browser
4. **Robust ADB Connectivity**: Reliable connections with automatic retries
5. **Screenshot Functionality**: API can capture screenshots from emulators
6. **Windows Compatibility**: Proper PowerShell environment variable handling
7. **Better Error Messages**: Clear indication of connection issues and status

## Platform-Specific Notes

### Windows Users
- **PowerShell Integration**: The API now properly sets `$env:ANDROID_ADB_SERVER_PORT`
- **Process Management**: Enhanced Windows process cleanup with `taskkill`
- **Environment Variables**: Automatic shell environment configuration

### Unix/Linux/macOS Users  
- **Shell Integration**: Proper `export` command usage
- **Process Management**: Enhanced `pkill` usage for ADB cleanup
- **Environment Variables**: Standard bash environment setup

## Troubleshooting

### If containers don't start:
1. Check Docker logs: `docker-compose logs emulator`
2. Ensure sufficient system resources (RAM, CPU)
3. Verify Android SDK images are properly installed

### If API can't discover containers:
1. Make sure containers are running: `docker ps`
2. Manually trigger discovery: `POST /api/containers/discover`
3. Check container names match the patterns in `PREDEFINED_CONTAINERS`

### If ADB fails (IMPROVED):
1. **Run ADB test script**: `python test_adb_windows.py`
2. **Check port accessibility**: Verify ADB ports are mapped correctly
3. **Force reconnection**: `POST /api/emulators/{id}/reconnect`
4. **Check device boot status**: Wait for `boot_completed` property
5. **Review logs**: Check API logs for detailed error messages

### If VNC doesn't work:
1. Check if VNC ports are accessible: `telnet localhost 5901`
2. Look at container logs for VNC startup messages
3. Ensure X11 and window manager are properly started in containers

### Windows-Specific Issues (NEW):
1. **PowerShell Execution Policy**: Ensure PowerShell can execute commands
2. **ADB PATH**: Verify ADB is in Windows PATH
3. **Port Conflicts**: Check for port conflicts with Windows services
4. **Firewall**: Ensure Windows Firewall allows Docker port access

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

## New API Endpoints

- `POST /api/containers/discover` - Manually discover containers
- `POST /api/emulators/{id}/reconnect` - Force ADB reconnection with robust restart
- `GET /api/emulators/{id}/status` - Enhanced status with device detection
- `GET /api/emulators/{id}/screenshot` - Improved screenshot with robust ADB

## Next Steps

1. **Restart containers**: `docker-compose down && docker-compose up -d`
2. **Run comprehensive tests**: `python test_adb_windows.py`
3. **Validate all functionality**: `python test_fixes.py`
4. **Access web interface**: http://localhost:5001
5. **Use VNC viewers**: http://localhost:5001/vnc/{emulator_id}
6. **Test screenshots**: via API endpoints

The enhanced fixes provide **robust, cross-platform ADB connectivity** with **intelligent retry mechanisms** and **detailed error reporting**, specifically addressing the Windows compatibility issues and unreliable device detection problems seen in the original logs. 