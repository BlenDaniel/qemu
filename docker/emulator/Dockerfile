FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install prerequisites 
RUN apt-get update && \
    apt-get install -y \
    wget unzip openjdk-11-jdk \
    curl libpulse0 libc++1 libgl1 libnss3 libxcomposite1 libxcursor1 libxi6 \
    libxtst6 libasound2 libxrandr2 libxdamage1 libxfixes3 libxrender1 \
    libfontconfig1 libsm6 libice6 libdbus-1-3 libxcb1 \
    android-tools-adb android-sdk-platform-tools-common \
    netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

# Set SDK paths and environment variables
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH=$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/emulator

# Create the SDK directory with proper permissions
RUN mkdir -p ${ANDROID_SDK_ROOT} && \
    chmod -R 777 ${ANDROID_SDK_ROOT}

# Install Android command-line tools
RUN mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools && \
    wget -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O /tmp/cmdline-tools.zip && \
    unzip -q /tmp/cmdline-tools.zip -d /tmp && \
    mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools/latest && \
    mv /tmp/cmdline-tools/* ${ANDROID_SDK_ROOT}/cmdline-tools/latest/ && \
    rm -rf /tmp/cmdline-tools*

# Accept licenses and install core SDK & emulator
RUN mkdir -p ~/.android && touch ~/.android/repositories.cfg && \
    yes | ${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager --licenses && \
    ${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager \
      "platform-tools" \
      "emulator" \
      "system-images;android-30;google_apis;x86" \
      "build-tools;30.0.3" \
      "platforms;android-30"

# Create AVD
RUN echo "no" | avdmanager create avd -n test -k "system-images;android-30;google_apis;x86" --force

# Copy entrypoint script
COPY adb/start-emulator.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/start-emulator.sh

# Expose ports: console, ADB, ADB-server
EXPOSE 5554 5555 5037

WORKDIR ${ANDROID_SDK_ROOT}
CMD ["/usr/local/bin/start-emulator.sh"]