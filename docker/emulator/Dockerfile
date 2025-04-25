FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive
ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_HOME=${ANDROID_HOME}
ENV ANDROID_SDK_ROOT=${ANDROID_HOME}
ENV PATH=${PATH}:${ANDROID_HOME}/tools/bin:${ANDROID_HOME}/platform-tools

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    openjdk-8-jdk \
    unzip \
    libglu1 \
    libpulse0 \
    libasound2 \
    libxi6 \
    libxcursor1 \
    libxdamage1 \
    libxrandr2 \
    libxcomposite1 \
    libc6 \
    libncurses5 \
    libstdc++6 \
    zlib1g \
    libx11-6 \
    android-tools-adb \
    android-tools-fastboot \
    qemu-kvm \
    libvirt-bin \
    ubuntu-vm-builder \
    bridge-utils \
    iptables \
    socat \
    netcat \
    net-tools \
    lsof \
    && rm -rf /var/lib/apt/lists/*

# Setup working directory
WORKDIR /opt

# Download and setup Android SDK
RUN curl -o sdk-tools.zip https://dl.google.com/android/repository/sdk-tools-linux-4333796.zip \
    && unzip sdk-tools.zip -d ${ANDROID_HOME} \
    && rm sdk-tools.zip \
    && mkdir -p ${ANDROID_HOME}/.android/ \
    && touch ${ANDROID_HOME}/.android/repositories.cfg

# Accept licenses
RUN yes | sdkmanager --licenses

# Install platform-tools and system-images
RUN sdkmanager "platform-tools" "platforms;android-29" "system-images;android-29;google_apis;x86_64"

# Create and configure emulator
RUN echo "no" | avdmanager create avd -n test -k "system-images;android-29;google_apis;x86_64" --device "pixel_xl"

# Set up a script to start the emulator
COPY emulator/adb/start-emulator.sh /opt/start-emulator.sh
RUN chmod +x /opt/start-emulator.sh

# Set up ADB port forwarding script
COPY emulator/adb/port-forward.sh /opt/port-forward.sh
RUN chmod +x /opt/port-forward.sh

# Expose ports
# ADB server port
EXPOSE 5037/tcp
# Emulator console port
EXPOSE 5554/tcp
# ADB connection port 
EXPOSE 5555/tcp

# Start the emulator and ADB forwarding
CMD ["/bin/bash", "-c", "/opt/start-emulator.sh & /opt/port-forward.sh"]