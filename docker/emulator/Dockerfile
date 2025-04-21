FROM ubuntu:25.04

ENV DEBIAN_FRONTEND=noninteractive

# Install prerequisites
RUN apt-get update && \
    apt-get install -y \
    wget unzip openjdk-11-jdk qemu-kvm libvirt-clients libvirt-daemon-system \
    curl libpulse0 libc++1 libgl1 libnss3 libxcomposite1 libxcursor1 libxi6 \
    libxtst6 libasound2t64 libxrandr2 libxdamage1 libxfixes3 libxrender1 \
    libfontconfig1 libsm6 libice6 libdbus-1-3 libxcb1 \
    netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

# Set SDK paths and environment variables
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH=$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/emulator

# Create the SDK directory
RUN mkdir -p ${ANDROID_SDK_ROOT}

# Install Android command-line tools (fix folder structure)
RUN mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools && \
    wget -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O /tmp/cmdline-tools.zip && \
    unzip -q /tmp/cmdline-tools.zip -d /tmp && \
    mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools/latest && \
    mv /tmp/cmdline-tools/* ${ANDROID_SDK_ROOT}/cmdline-tools/latest/ && \
    rm -rf /tmp/cmdline-tools* 

# Accept licenses
RUN mkdir -p ~/.android && touch ~/.android/repositories.cfg && \
    yes | sdkmanager --licenses

# Install platform-tools, platforms, build-tools
RUN sdkmanager "platform-tools" "platforms;android-29" "build-tools;29.0.3"

# Install emulator
RUN sdkmanager "emulator"

# Install system image
RUN sdkmanager "system-images;android-29;google_apis;x86_64"

# Create AVD
RUN echo "no" | avdmanager create avd \
    --name "test" \
    --package "system-images;android-29;google_apis;x86_64" \
    --device "pixel" \
    --force

# Expose emulator and ADB ports
EXPOSE 5554 5555 5556 5557

# Healthcheck for emulator
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD nc -z 127.0.0.1 5554 || exit 1

# Start the emulator
CMD ["sh", "-c", "emulator -avd test -no-window -no-audio -gpu off -no-boot-anim -port 5554 -accel off & sleep 15 && tail -f /dev/null"]
