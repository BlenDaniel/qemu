FROM ubuntu:22.04
WORKDIR /app

ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Update package lists first
RUN apt-get update

# Install ca-certificates FIRST, then update certificates
RUN apt-get install -y ca-certificates && update-ca-certificates

# Install basic packages
RUN apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    unzip \
    curl \
    git

# Install build tools
RUN apt-get install -y \
    gcc \
    build-essential \
    zlib1g-dev \
    libjpeg-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libtiff5-dev

# Install network tools
RUN apt-get install -y \
    netcat-openbsd \
    telnet \
    iputils-ping \
    net-tools

# Install Java and VNC tools
RUN apt-get install -y \
    openjdk-17-jre-headless \
    tigervnc-viewer \
    tigervnc-common \
    websockify

# Install Docker repository setup tools
RUN apt-get install -y \
    apt-transport-https \
    gnupg \
    lsb-release

# Add Docker repository and install Docker CLI (with SSL fix)
RUN curl -fsSL https://get.docker.com | sh

# Clean up
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Android SDK Platform Tools (includes ADB)
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV PATH=${PATH}:${ANDROID_SDK_ROOT}/platform-tools

RUN mkdir -p ${ANDROID_SDK_ROOT} && \
    cd ${ANDROID_SDK_ROOT} && \
    wget --no-check-certificate https://dl.google.com/android/repository/platform-tools-latest-linux.zip && \
    unzip platform-tools-latest-linux.zip && \
    rm platform-tools-latest-linux.zip && \
    chmod +x platform-tools/adb

COPY requirements.txt .

RUN python3 -m pip install --upgrade pip

RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY docker_manager.py .
COPY adb_manager.py .
COPY vnc_manager.py .
COPY websocket_manager.py .
COPY api_routes.py .
COPY templates/ templates/
COPY static/ static/

# Download and setup noVNC
RUN cd /opt && \
    git clone https://github.com/novnc/noVNC.git && \
    cd noVNC && \
    git checkout v1.4.0 && \
    ln -s vnc.html index.html

CMD ["python3", "-m", "flask", "run", "--host=0.0.0.0", "--port=5001"]