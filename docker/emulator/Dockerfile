FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install prerequisites with added dependencies for timezone, audio, and graphics
RUN apt-get update && \
    apt-get install -y \
    ca-certificates wget unzip openjdk-11-jdk \
    curl libpulse0 libc++1 libgl1 libnss3 libxcomposite1 libxcursor1 libxi6 \
    libxtst6 libasound2 libxrandr2 libxdamage1 libxfixes3 libxrender1 \
    libfontconfig1 libsm6 libice6 libdbus-1-3 libxcb1 \
    libegl1-mesa libgbm1 libvulkan1 mesa-vulkan-drivers \
    android-tools-adb android-sdk-platform-tools-common \
    pulseaudio tzdata alsa-utils netcat-openbsd dos2unix iptables socat net-tools && \
    rm -rf /var/lib/apt/lists/*

# Set SDK paths and environment variables
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH=$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/emulator

# Create the SDK directory with proper permissions
RUN mkdir -p ${ANDROID_SDK_ROOT} && \
    chmod -R 777 ${ANDROID_SDK_ROOT}

# Install Android command-line tools
RUN apt-get update && apt-get install -y ca-certificates && \
    mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools && \
    wget --no-check-certificate -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O /tmp/cmdline-tools.zip && \
    unzip -q /tmp/cmdline-tools.zip -d /tmp && \
    mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools/latest && \
    mv /tmp/cmdline-tools/* ${ANDROID_SDK_ROOT}/cmdline-tools/latest/ && \
    rm -rf /tmp/cmdline-tools*

# Accept licenses and install core SDK & emulator
RUN mkdir -p ~/.android && touch ~/.android/repositories.cfg && \
    yes | ${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager --licenses --no_https --verbose && \
    ${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager --no_https --verbose \
    "platform-tools" \
    "emulator" \
    "system-images;android-30;google_apis;x86" \
    "build-tools;30.0.3" \
    "platforms;android-30"

# Verify ADB is installed properly and create symlinks if needed
RUN if [ ! -e "${ANDROID_SDK_ROOT}/platform-tools/adb" ]; then \
    echo "ERROR: ADB not found in expected location"; \
    exit 1; \
    else \
    echo "ADB found at ${ANDROID_SDK_ROOT}/platform-tools/adb"; \
    ln -sf ${ANDROID_SDK_ROOT}/platform-tools/adb /usr/local/bin/adb; \
    fi && \
    if [ ! -e "${ANDROID_SDK_ROOT}/emulator/emulator" ]; then \
    echo "ERROR: Emulator not found in expected location"; \
    exit 1; \
    else \
    echo "Emulator found at ${ANDROID_SDK_ROOT}/emulator/emulator"; \
    ln -sf ${ANDROID_SDK_ROOT}/emulator/emulator /usr/local/bin/emulator; \
    fi

# Fix timezone issues
RUN ln -snf /usr/share/zoneinfo/Etc/UTC /etc/localtime && \
    echo "Etc/UTC" > /etc/timezone

# Configure audio
RUN mkdir -p /root/.config/pulse && \
    echo "default-server = unix:/tmp/pulseaudio.socket" > /root/.config/pulse/client.conf

# Create AVD with optimized settings
RUN echo "no" | avdmanager create avd -n test -k "system-images;android-30;google_apis;x86" --force && \
    echo "hw.audioInput=no" >> ~/.android/avd/test.avd/config.ini && \
    echo "hw.audioOutput=no" >> ~/.android/avd/test.avd/config.ini && \
    echo "hw.gpu.enabled=yes" >> ~/.android/avd/test.avd/config.ini && \
    echo "hw.gpu.mode=swiftshader_indirect" >> ~/.android/avd/test.avd/config.ini && \
    echo "hw.ramSize=1536" >> ~/.android/avd/test.avd/config.ini

# Create Android config directory and ensure proper permissions
RUN mkdir -p /root/.android && \
    chmod -R 755 /root/.android

# Create and proper directory for scripts
RUN mkdir -p /usr/local/bin

# Copy entrypoint scripts - using absolute path to avoid issues
COPY adb/start-emulator.sh /usr/local/bin/
COPY adb/port-forward.sh /usr/local/bin/

# Fix line endings and ensure scripts are executable
RUN dos2unix /usr/local/bin/start-emulator.sh && \
    dos2unix /usr/local/bin/port-forward.sh && \
    chmod +x /usr/local/bin/start-emulator.sh && \
    chmod +x /usr/local/bin/port-forward.sh && \
    ls -la /usr/local/bin/

# Create backup copies of the scripts in case the originals are not found
RUN cp /usr/local/bin/start-emulator.sh /start-emulator.sh && \
    cp /usr/local/bin/port-forward.sh /port-forward.sh && \
    chmod +x /start-emulator.sh && \
    chmod +x /port-forward.sh

# Verify ADB and emulator are in PATH
RUN which adb || echo "WARNING: adb not in PATH" && \
    which emulator || echo "WARNING: emulator not in PATH" && \
    adb version || echo "WARNING: adb command failed" && \
    ls -la /usr/local/bin/

# Expose ports: console, ADB, ADB-server
# 5037: ADB server
# 5554: Emulator console
# 5555: ADB over TCP/IP
# Important: Make all ports available for binding on 0.0.0.0 to ensure they're accessible from outside
EXPOSE 5037/tcp 5554/tcp 5555/tcp

WORKDIR ${ANDROID_SDK_ROOT}
# Run just the start-emulator.sh script since we've integrated port forwarding
CMD ["/bin/bash", "-c", "if [ -x /usr/local/bin/start-emulator.sh ]; then /usr/local/bin/start-emulator.sh; else /start-emulator.sh; fi"]