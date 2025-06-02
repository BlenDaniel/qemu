FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
# Enable external ADB connectivity
ENV ENABLE_EXTERNAL_ADB=true

# Install prerequisites with added dependencies for timezone, audio, and graphics
# Added network tools for better diagnostics and ADB connectivity
RUN apt-get update && \
    apt-get install -y \
    ca-certificates wget unzip openjdk-11-jdk \
    curl libpulse0 libc++1 libgl1 libnss3 libxcomposite1 libxcursor1 libxi6 \
    libxtst6 libasound2 libxrandr2 libxdamage1 libxfixes3 libxrender1 \
    libfontconfig1 libsm6 libice6 libdbus-1-3 libxcb1 \
    libegl1-mesa libgbm1 libvulkan1 mesa-vulkan-drivers \
    android-tools-adb android-sdk-platform-tools-common \
    pulseaudio tzdata alsa-utils netcat-openbsd dos2unix iptables socat \
    net-tools iproute2 iputils-ping lsof tcpdump \
    # Adding specific Vulkan packages
    libvulkan-dev vulkan-tools vulkan-validationlayers \
    # VNC and X11 support for GUI forwarding
    x11vnc xvfb fluxbox dbus-x11 xfonts-base xfonts-scalable \
    && rm -rf /var/lib/apt/lists/*

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

# Create symlinks for Vulkan libraries
RUN ln -sf /usr/lib/x86_64-linux-gnu/libvulkan.so.1 /usr/lib/x86_64-linux-gnu/libvulkan.so && \
    ln -sf /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ${ANDROID_SDK_ROOT}/emulator/lib64/vulkan/libvulkan.so && \
    ln -sf /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ${ANDROID_SDK_ROOT}/emulator/lib64/vulkan/libvulkan.so.1 && \
    mkdir -p ${ANDROID_SDK_ROOT}/emulator/qemu/linux-x86_64/lib64/vulkan/ && \
    ln -sf /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ${ANDROID_SDK_ROOT}/emulator/qemu/linux-x86_64/lib64/vulkan/libvulkan.so && \
    ln -sf /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ${ANDROID_SDK_ROOT}/emulator/qemu/linux-x86_64/lib64/vulkan/libvulkan.so.1

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

# Copy entrypoint scripts - using absolute path to avoid issues
COPY adb/start-emulator.sh /usr/local/bin/


# Fix line endings and ensure scripts are executable
RUN dos2unix /usr/local/bin/start-emulator.sh && \
    chmod +x /usr/local/bin/start-emulator.sh && \
    ls -la /usr/local/bin/

# Create backup copies of the scripts in case the originals are not found
RUN cp /usr/local/bin/start-emulator.sh /start-emulator.sh && \
    chmod +x /start-emulator.sh


    # Expose ports: console, ADB, ADB-server, VNC
EXPOSE 5554 5555 5037 5900

WORKDIR ${ANDROID_SDK_ROOT}
CMD ["/usr/local/bin/start-emulator.sh"]