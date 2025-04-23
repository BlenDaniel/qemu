#!/bin/bash
# ADB Manager - Essential tool for managing ADB connections to emulators

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

API_ENDPOINT="http://localhost:5001"

function help {
  echo -e "${BLUE}ADB Manager - Usage:${NC}"
  echo "  $0 connect    - Connect to all emulators"
  echo "  $0 connect PORT - Connect to a specific port (e.g., $0 connect 32770)"
  echo "  $0 status     - Show connection status"
  echo "  $0 restart    - Restart ADB and reconnect"
  echo "  $0 create     - Create a new emulator"
  echo "  $0 watch      - Watch and maintain connections"
}

function connect_port {
  PORT=$1
  
  if [ -z "$PORT" ]; then
    echo -e "${RED}Error: No port specified${NC}"
    echo -e "Usage: $0 connect PORT"
    return 1
  fi
  
  echo -e "${YELLOW}Connecting to emulator on port $PORT...${NC}"
  
  # Try to connect to the specific port
  RESULT=$(adb connect localhost:$PORT)
  
  if [[ $RESULT == *"connected"* ]] && [[ ! $RESULT == *"failed"* ]]; then
    echo -e "${GREEN}✅ Successfully connected to port $PORT${NC}"
    echo -e "${GREEN}$RESULT${NC}"
  else
    echo -e "${RED}❌ Failed to connect to port $PORT${NC}"
    echo -e "${RED}$RESULT${NC}"
    echo -e "\n${YELLOW}Trying to fix connection...${NC}"
    
    # Try to fix by restarting ADB
    adb kill-server
    sleep 1
    adb start-server
    sleep 1
    
    # Try to connect again
    RESULT=$(adb connect localhost:$PORT)
    
    if [[ $RESULT == *"connected"* ]] && [[ ! $RESULT == *"failed"* ]]; then
      echo -e "${GREEN}✅ Successfully connected after restart${NC}"
      echo -e "${GREEN}$RESULT${NC}"
    else
      echo -e "${RED}❌ Still failed to connect after restart${NC}"
      echo -e "${RED}$RESULT${NC}"
    fi
  fi
  
  # Show current connected devices
  echo -e "\n${YELLOW}Current connected devices:${NC}"
  adb devices
}

function connect {
  # If a port is specified, connect to that port only
  if [ ! -z "$1" ]; then
    connect_port "$1"
    return
  fi

  echo -e "${YELLOW}Connecting to all emulators...${NC}"
  
  # Get emulators from API and connect to each one
  EMULATORS=$(curl -s "$API_ENDPOINT/emulators")
  
  if [ -z "$EMULATORS" ] || [ "$EMULATORS" = "{}" ]; then
    echo -e "${RED}No emulators found${NC}"
    return
  fi
  
  # Use Python to parse JSON and connect to each emulator
  echo "$EMULATORS" | python3 -c '
import json, sys, os, subprocess
data = json.load(sys.stdin)
success = 0
failed = 0

for emu_id, info in data.items():
    conn_info = info.get("connection_info", {})
    adb_cmd = conn_info.get("adb_command", "")
    port = conn_info.get("mapped_adb_port", "")
    
    if adb_cmd and port:
        print(f"Connecting to emulator {emu_id[:8]}... on port {port}")
        result = subprocess.run(adb_cmd.split(), capture_output=True, text=True)
        if "connected" in result.stdout.lower() and "failed" not in result.stdout.lower():
            print(f"\033[0;32m✅ Success: {result.stdout.strip()}\033[0m")
            success += 1
        else:
            print(f"\033[0;31m❌ Failed: {result.stdout.strip()}\033[0m")
            failed += 1

print(f"\033[0;34mSummary: {success} connected, {failed} failed\033[0m")
'
}

function status {
  echo -e "${YELLOW}Current ADB connections:${NC}"
  adb devices
  
  echo -e "\n${YELLOW}API status:${NC}"
  curl -s "$API_ENDPOINT/healthcheck" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    stats = data["stats"]
    print(f"  Total emulators: {stats.get(\"total_emulators\", 0)}")
    print(f"  Connected devices: {stats.get(\"connected_devices\", 0)}")
    print(f"  Offline devices: {stats.get(\"offline_devices\", 0)}")
except Exception as e:
    print(f"  Error: {str(e)}")
'
}

function restart {
  echo -e "${YELLOW}Restarting ADB server...${NC}"
  adb kill-server
  sleep 1
  adb start-server
  sleep 1
  connect
}

function create {
  echo -e "${YELLOW}Creating new emulator...${NC}"
  RESULT=$(curl -s -X POST "$API_ENDPOINT/emulators")
  echo "$RESULT" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(f"\033[0;32mEmulator created!\033[0m")
    print(f"  ID: {data.get(\"id\", \"unknown\")}")
    conn_info = data.get("connection_info", {})
    print(f"  Connection: {conn_info.get(\"adb_command\", \"unknown\")}")
    print(f"  Status: {conn_info.get(\"auto_connection_status\", \"unknown\")}")
except Exception as e:
    print(f"Error: {str(e)}")
'
}

function watch {
  echo -e "${BLUE}Starting connection watcher (Ctrl+C to stop)${NC}"
  while true; do
    TIMESTAMP=$(date +"%H:%M:%S")
    echo -e "${YELLOW}[$TIMESTAMP] Checking connections...${NC}"
    curl -s "$API_ENDPOINT/healthcheck?fix=true" > /dev/null
    status
    sleep 30
  done
}

# Main command processing
case "$1" in
  connect)  
    if [ ! -z "$2" ]; then
      connect "$2"
    else
      connect
    fi
    ;;
  status)   status ;;
  restart)  restart ;;
  create)   create ;;
  watch)    watch ;;
  *)        help ;;
esac 