#!/bin/bash
set -e

echo "Launching Android emulator AVD 'test'..."
emulator -avd test -no-window -gpu swiftshader_indirect -port 5554 &
EMU_PID=$!
echo "Waiting for emulator to boot..."
adb -a start-server
adb wait-for-device
until [[ "$(adb -a shell getprop sys.boot_completed)" == "1" ]]; do
  sleep 1
done
echo "Emulator booted."
echo "Listing devices:"
adb start-server
adb devices

echo "Emulator cannot be run directly due to architecture compatibility issues."
echo "For testing Android applications, consider using these alternatives:"

echo "1. Running ADB commands to devices connected to the host"
echo "2. Using Firebase Test Lab for cloud-based testing"
echo "3. Using a web-based emulator service"

echo "This container now provides ADB services on port 5037."
echo "You can connect to it from your development environment."

# Keep container running
tail -f /dev/null