# Container Discovery & ADB Connection Fixes

## 🔍 **Issues Identified from Logs:**

### From `api.log.bak`:
1. **Wrong container names**: API looking for `qemu-main-emulator` but actual containers are `qemu-emulator-1`
2. **Creating new containers**: API creating `emu_0lk0pzw8_c1e51978` instead of using existing ones
3. **Port confusion**: Trying to connect to port 5856 instead of the correct docker-compose ports
4. **Connection refused**: ADB getting "Connection refused" when trying to connect

### From `emulator.log.bak`:
1. **Emulator IS working**: VNC started on port 5900 ✅
2. **Android booted successfully**: "Emulator booted successfully" ✅
3. **ADB device available**: `emulator-5554` on port 5555 ✅
4. **Correct ADB advice**: "You can connect to it from your host using: adb connect localhost:5555" ✅

## 🔧 **Root Cause:**

The API container discovery function had **incorrect container name patterns** and wasn't finding the existing docker-compose containers, so it was creating new ones instead.

## ✅ **Fixes Applied:**

### 1. **Fixed Container Name Patterns**
```python
# BEFORE (incorrect):
"container_name_pattern": "qemu-main-emulator"
"container_name_pattern": "qemu-main-emulator14"

# AFTER (correct):
"container_name_pattern": "qemu-emulator-1"  # Fixed: actual container name
"container_name_pattern": "qemu-emulator14-1"  # Fixed: actual container name
```

### 2. **Improved Container Discovery Logic**
- **Flexible name matching**: Now checks for exact match OR partial match
- **Better logging**: Shows which containers are found and registered
- **Duplicate prevention**: Skips already registered containers
- **Reduced ADB retries**: During startup to avoid long delays

### 3. **Enhanced Port Handling**
- **Predefined containers**: Use static port configuration from docker-compose
- **Dynamic containers**: Use Docker API port mapping
- **Proper distinction**: Track which containers are predefined vs dynamic

### 4. **Better Error Handling**
- **Non-blocking registration**: Allow container registration even if ADB initially fails
- **Detailed logging**: Show success/failure of each step
- **Graceful degradation**: Continue discovery if one container fails

## 🚀 **How to Test the Fixes:**

### 1. **Restart the API container to apply changes:**
```bash
# Restart just the API container to pick up the code changes
docker-compose restart api

# Or restart all containers if needed
docker-compose down && docker-compose up -d
```

### 2. **Wait for emulators to fully boot (2-3 minutes)**

### 3. **Run the container discovery test:**
```bash
python test_container_discovery.py
```

### 4. **Manual API testing:**
```bash
# Trigger container discovery
curl -X POST http://localhost:5001/api/containers/discover

# List discovered emulators
curl http://localhost:5001/api/emulators

# Check status of a specific emulator
curl http://localhost:5001/api/emulators/{session_id}/status

# Force reconnection if needed
curl -X POST http://localhost:5001/api/emulators/{session_id}/reconnect
```

## 📊 **Expected Results After Fixes:**

### ✅ **Container Discovery Should Show:**
```json
{
  "success": true,
  "message": "Container discovery completed",
  "discovered_sessions": [
    "existing_emulator_android11_main",
    "existing_emulator14_android14_main"
  ]
}
```

### ✅ **Emulator List Should Show:**
```json
{
  "existing_emulator_android11_main": {
    "device_id": "android11_main",
    "android_version": "11",
    "container_name": "qemu-emulator-1",
    "status": "running",
    "is_predefined": true,
    "ports": {
      "console": "5554",
      "adb": "5555",
      "adb_server": "5037",
      "vnc": "5901"
    }
  },
  "existing_emulator14_android14_main": {
    "device_id": "android14_main", 
    "android_version": "14",
    "container_name": "qemu-emulator14-1",
    "status": "running",
    "is_predefined": true,
    "ports": {
      "console": "6654",
      "adb": "6655", 
      "adb_server": "6037",
      "vnc": "5902"
    }
  }
}
```

### ✅ **ADB Connection Should Work:**
- **Device Status**: "device" (not "not_found")
- **Boot Completed**: true
- **Android Version**: Detected (e.g., "11" or "14")

### ✅ **VNC Access Should Work:**
- **Android 11**: http://localhost:5001/vnc/existing_emulator_android11_main
- **Android 14**: http://localhost:5001/vnc/existing_emulator14_android14_main

### ✅ **Screenshots Should Work:**
- No more "Connection refused" errors
- Successful screenshot capture

## 🐞 **Troubleshooting:**

### If containers still not discovered:
```bash
# Check actual container names
docker ps

# Check API logs for discovery process
docker logs qemu-api-1

# Manually trigger discovery
curl -X POST http://localhost:5001/api/containers/discover
```

### If ADB still fails:
```bash
# Wait longer for emulator boot
# Check emulator logs
docker logs qemu-emulator-1
docker logs qemu-emulator14-1

# Force reconnection
curl -X POST http://localhost:5001/api/emulators/{session_id}/reconnect
```

### If VNC doesn't work:
```bash
# Check VNC ports are accessible
telnet localhost 5901  # Android 11
telnet localhost 5902  # Android 14

# Check container status
docker ps
```

## 🎯 **Key Changes Summary:**

1. **✅ Fixed container name patterns** to match actual Docker containers
2. **✅ Improved discovery logic** with flexible matching
3. **✅ Enhanced port handling** for predefined vs dynamic containers  
4. **✅ Better error handling** and logging
5. **✅ Created comprehensive test suite** for validation

The API should now properly discover and connect to your existing docker-compose emulator containers instead of creating new ones! 