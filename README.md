# QEMU-Based Multi-Tenant Android Emulator Farm

This project provides a Dockerized, API-driven emulator farm using QEMU and the Android SDK. Launch multiple headless Android emulators, connect via ADB, install APKs, run tests, and collect results—all programmatically.

## Prerequisites

- Linux host with KVM nested virtualization (recommended) OR macOS with Docker Desktop
- Docker & Docker Compose v2+
- (Optional) Android platform-tools on host: `brew install android-platform-tools` or `sudo apt install adb` or `choco install android-sdk` or `choco install android-sdk-platform-tools-common` (for windows)
- choco install jq -y


## Services

- **emulator**: Ubuntu container with Android SDK, QEMU emulator, and an x86 API 30 system image
  - Exposes ports:
    - 5554: emulator console
    - 5555: emulator ADB
    - 5037: ADB server
- **api**: Flask service on port 5001 to manage emulator sessions via REST

## Quick Start

```bash
git clone <repo_url>  # or your project path
cd QEMU
docker compose up --build -d
```

Verify:
```bash
docker compose ps
# qemu-emulator-1 Up (healthy)
# qemu-api-1      Up 5001/tcp
```

## Emulator API

- **Create session**
  ```bash
  curl -s -X POST http://localhost:5001/emulators | jq .
  ```
  or
  ```bash
   Invoke-WebRequest -Method Post -Uri http://localhost:5001/emulators | Select-Object -ExpandProperty Content | jq .
  ```
  Response:
  ```json
  {
    "id": "<SESSION_ID>",
    "ports": {
      "5554/tcp": [{"HostPort":"<PORT_5554>"}],
      "5555/tcp": [{"HostPort":"<PORT_5555>"}],
      "5037/tcp": [{"HostPort":"<PORT_5037>"}]
    }
  }
  ```

- **List sessions**
  ```bash
  curl http://localhost:5001/emulators | jq .
  ```

  ```bash
  Invoke-WebRequest -Method Get -Uri http://localhost:5001/emulators  
  ```
- **Delete session**
  ```bash
  curl -X DELETE http://localhost:5001/emulators/<SESSION_ID>
  ```

## Connecting via ADB

Choose one:

1. **Direct emulator ADB port**
   ```bash
   adb connect localhost:<PORT_5555>
   ```
2. **Container ADB server**
   ```bash
   export ADB_SERVER_SOCKET=tcp:localhost:<5037>; adb kill-server; adb start-server; adb devices
   ```

# Wait for boot and run tests:

```bash
  adb -s localhost:32770 wait-for-device 
  until [ "$(adb -s localhost:32770 shell getprop sys.boot_completed)" = "1" ]; do sleep 1; done
  adb -s localhost:<PORT_5555> install app.apk

  adb kill-server && adb start-server
  adb devices
```

## Boot & Test Workflow

Wait for boot:
```bash
adb -s localhost:<PORT_5555> wait-for-device
until [ "$(adb -s localhost:<PORT_5555> shell getprop sys.boot_completed)" = "1" ]; do sleep 1; done
```

Install APK and run tests:
```bash
adb -s localhost:<PORT_5555> 
adb -s localhost:<PORT_5555> shell am instrument -w <TEST_RUNNER>
adb -s localhost:<PORT_5555> pull /sdcard/results.xml .
```

## Cleanup

```bash
docker compose down --volumes
docker system prune -af
```

## Running with Vagrant + KVM (Recommended)

This project provides a Vagrantfile to spin up a Linux VM (Ubuntu 20.04) with KVM enabled, Docker, and Docker Compose. It will automatically build and launch the emulator farm inside the VM. Ports 5554, 5555, 5037, and 5001 are forwarded to your host.

### Prerequisites

- Host machine with KVM support
- Vagrant
- vagrant-libvirt plugin (`vagrant plugin install vagrant-libvirt`)

### Usage

```bash
git clone <repo_url>
cd QEMU
vagrant up
```

This will provision the VM, install necessary packages, and start the emulator and API services. To verify:

```bash
docker-compose ps
# qemu-emulator-1 Up (healthy)
# qemu-api-1      Up 5001/tcp
```

### VM Cleanup

To destroy the VM and remove resources:

```bash
vagrant destroy -f
```