#!/bin/bash
set -e

# Initialize VNC server if ENABLE_VNC is set
if [ "${ENABLE_VNC}" = "true" ]; then
    echo "Setting up VNC server for GUI access..."
    
    # Create Fluxbox config directory and basic configuration to suppress warnings
    mkdir -p /root/.fluxbox
    cat > /root/.fluxbox/init << 'EOF'
session.screen0.slit.acceptKdeDockapps: false
session.screen0.slit.autoHide: false
session.screen0.slit.maxOver: false
session.screen0.slit.placement: RightBottom
session.screen0.slit.alpha: 255
session.screen0.slit.onhead: 1
session.screen0.slit.layer: Dock
session.screen0.toolbar.autoHide: false
session.screen0.toolbar.maxOver: false
session.screen0.toolbar.visible: true
session.screen0.toolbar.alpha: 255
session.screen0.toolbar.layer: Dock
session.screen0.toolbar.onhead: 1
session.screen0.toolbar.placement: TopCenter
session.screen0.toolbar.height: 0
session.screen0.iconbar.mode: {static groups}
session.screen0.iconbar.alignment: Relative
session.screen0.iconbar.iconWidth: 70
session.screen0.iconbar.iconTextPadding: 10
session.screen0.iconbar.usePixmap: true
session.screen0.titlebar.left: Shade Minimize Maximize Close
session.screen0.titlebar.right: Stick
EOF

    # Start Xvfb (virtual framebuffer X server)
    export DISPLAY=:1
    echo "Starting Xvfb virtual display..."
    Xvfb :1 -screen 0 1024x768x24 -ac +extension GLX +render -noreset &
    XVFB_PID=$!
    
    # Wait for Xvfb to start
    sleep 3
    
    # Start window manager with suppressed output
    echo "Starting Fluxbox window manager..."
    fluxbox -display :1 >/dev/null 2>&1 &
    FLUXBOX_PID=$!
    
    # Wait for window manager to initialize
    sleep 2
    
    # Start VNC server with optimized settings
    VNC_PORT=${VNC_PORT:-5900}
    echo "Starting VNC server on port $VNC_PORT..."
    x11vnc -display :1 -forever -nopw -listen localhost -xkb -rfbport $VNC_PORT \
           -shared -permitfiletransfer -tightfilexfer \
           -quiet >/dev/null 2>&1 &
    VNC_PID=$!
    
    echo "VNC server started on port $VNC_PORT"
    echo "VNC PIDs: Xvfb=$XVFB_PID, Fluxbox=$FLUXBOX_PID, VNC=$VNC_PID"
    
    # Set environment variables for emulator to use the display
    export DISPLAY=:1
fi

# List available system images
echo "Available system images:"
ls -la /opt/android-sdk/system-images/android-30/google_apis/x86/ || echo "x86 system image directory not found, checking parent directory..."
ls -la /opt/android-sdk/system-images/android-30/google_apis/ || echo "System images directory structure:"
find /opt/android-sdk/system-images/ -type d -name "*android-30*" 2>/dev/null || echo "No android-30 system images found"

# Ensure AVD directory exists
mkdir -p /root/.android/avd
chmod -R 755 /root/.android

# Get device ID from environment or use default
DEVICE_ID=${DEVICE_ID:-test}
echo "Using device ID: $DEVICE_ID"

# Clean up any existing AVD with the same name
rm -rf /root/.android/avd/${DEVICE_ID}.* /root/.android/avd/${DEVICE_ID}.avd

# Use the DEVICE_PORT from the environment if set, otherwise default to 5554
# This will determine the emulator-XXXX name seen in adb devices
EMULATOR_PORT=${DEVICE_PORT:-5554}
echo "Setting emulator port to: $EMULATOR_PORT (will appear as emulator-$EMULATOR_PORT)"

# Create a new AVD with the x86 system image (not x86_64)
echo "Creating AVD named '$DEVICE_ID' with x86 architecture..."
echo "no" | avdmanager create avd -n $DEVICE_ID -k "system-images;android-30;google_apis;x86" --force

# Apply optimized settings to config.ini
if [ -f "/root/.android/avd/${DEVICE_ID}.avd/config.ini" ]; then
  echo "Configuring emulator with optimized settings..."

  # Audio settings
  echo "hw.audioInput=no" >> /root/.android/avd/${DEVICE_ID}.avd/config.ini
  echo "hw.audioOutput=no" >> /root/.android/avd/${DEVICE_ID}.avd/config.ini
  
  # GPU settings
  sed -i 's/hw.gpu.enabled=.*/hw.gpu.enabled=yes/g' /root/.android/avd/${DEVICE_ID}.avd/config.ini
  sed -i 's/hw.gpu.mode=.*/hw.gpu.mode=swiftshader_indirect/g' /root/.android/avd/${DEVICE_ID}.avd/config.ini
  echo "hw.gpu.enabled=yes" >> /root/.android/avd/${DEVICE_ID}.avd/config.ini
  echo "hw.gpu.mode=swiftshader_indirect" >> /root/.android/avd/${DEVICE_ID}.avd/config.ini
  
  # RAM and performance settings
  echo "hw.ramSize=2048" >> /root/.android/avd/${DEVICE_ID}.avd/config.ini
  echo "hw.useext4=yes" >> /root/.android/avd/${DEVICE_ID}.avd/config.ini
  echo "hw.cpu.ncore=1" >> /root/.android/avd/${DEVICE_ID}.avd/config.ini
  echo "vm.heapSize=256" >> /root/.android/avd/${DEVICE_ID}.avd/config.ini
fi

echo "Launching Android emulator AVD '$DEVICE_ID' on port $EMULATOR_PORT..."

# Determine emulator launch parameters based on VNC setup
if [ "${ENABLE_VNC}" = "true" ]; then
    echo "Launching emulator with GUI support via VNC..."
    # Use the X display for GUI, but still use swiftshader for better compatibility
    emulator -avd $DEVICE_ID -no-audio -no-boot-anim \
      -gpu swiftshader_indirect -no-snapshot -noaudio \
      -no-snapshot-save -port $EMULATOR_PORT &
else
    echo "Launching emulator in headless mode..."
    # Use these flags to run with swiftshader indirect rendering
    emulator -avd $DEVICE_ID -no-window -no-audio -no-boot-anim \
      -gpu swiftshader_indirect -no-snapshot -noaudio \
      -no-snapshot-save -port $EMULATOR_PORT &
fi

EMU_PID=$!
echo "Waiting for emulator to boot..."

# Start ADB server quietly 
echo "Starting ADB server..."
adb -a start-server >/dev/null 2>&1
adb wait-for-device >/dev/null 2>&1 || true

# Try for a limited time to wait for emulator to boot
MAX_WAIT=120
COUNT=0
while [ $COUNT -lt $MAX_WAIT ]; do
  if adb -a shell getprop sys.boot_completed 2>/dev/null | grep -q "1"; then
    echo "Emulator booted successfully."
    break
  fi
  echo "Still waiting for emulator to boot... ($COUNT/$MAX_WAIT)"
  sleep 5
  COUNT=$((COUNT + 5))
done

if [ $COUNT -ge $MAX_WAIT ]; then
  echo "WARNING: Emulator failed to boot completely, but services should still be available."
fi

echo "Listing devices:"
adb start-server >/dev/null 2>&1
adb devices

echo "Emulator is now available via ADB as 'emulator-$EMULATOR_PORT'"
echo "You can connect to it from your host using: adb connect localhost:$((EMULATOR_PORT + 1))"
echo "Note: ADB connection port is always emulator port + 1"

# Set environment variable to make it easier to target this emulator in scripts
export ANDROID_SERIAL="emulator-$EMULATOR_PORT"
echo "Set ANDROID_SERIAL=$ANDROID_SERIAL for easier targeting in scripts"

# Keep container running
tail -f /dev/null