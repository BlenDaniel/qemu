## Roadmap: QEMU-Based Multi-Tenant Android Emulator Farm

This roadmap outlines the steps to build a scalable, automated Android emulator farm using QEMU, with a focus on multi-user support, automated testing, and a feature comparison with Google’s Android Test Station (ATS).

---

### **1. Environment & Prerequisites**

- **Server OS:** Linux (with KVM support recommended for hardware acceleration) [[5](https://developer.android.com/studio/run/emulator-acceleration)]
- **Hardware:** Minimum 4 CPU cores, nested virtualization enabled
- **Software to Install:**
  - QEMU/KVM
  - Android SDK (including emulator and platform-tools)
  - ADB (Android Debug Bridge)

---

### **2. Prototype: Single Headless Emulator**

- Download an Android x86 system image [[1](https://www.instructables.com/Creating-an-Android-Emulator-Using-Qemu/), [5](https://www.browserstack.com/android-emulators)]
- Create an Android Virtual Device (AVD) and launch it headlessly via QEMU
- Forward ADB ports (5554/5555) to allow remote `adb connect :` [[3](https://developer.android.com/studio/run/emulator-commandline)]
- Verify the workflow:
  - Install APKs: `adb install`
  - Run tests: `adb shell am instrument`
  - Pull logs/results: `adb pull /sdcard/results.xml`

---

### **3. Scale to Multiple Concurrent Instances**

- **Containerization:** Use Docker with KVM passthrough or spawn separate QEMU processes per emulator [[7](https://www.linaro.org/blog/qemu-a-tale-of-performance-analysis/)]
- **Session Management:**
  - Assign unique AVD names and TCP ports to each user/session
- **API/CLI Tooling:**
  - Develop a lightweight REST API or CLI script to request an emulator and return connection details

---

### **4. CI/Test Automation**

- Wrap test suite execution in a script or CI pipeline (e.g., Jenkinsfile) that:
  - Reserves an emulator via the farm API
  - Uploads APK(s)
  - Runs tests using `adb shell am instrument` or `adb shell monkey`
  - Collects logs/results
  - Releases the emulator for reuse

---

### **5. Results Dashboard & Visibility**

- Parse JUnit/XML results into HTML reports or integrate with dashboards (e.g., Allure, Jenkins)
- Optionally stream `adb logcat` or video recordings for live test monitoring

---

### **6. Feature-by-Feature Comparison: QEMU Farm vs. Android Test Station (ATS)**

| Feature                    | QEMU Emulator Farm                  | Android Test Station (ATS)          |
|----------------------------|-------------------------------------|-------------------------------------|
| Multi-device support       | Yes (customizable)                  | Yes (built-in)                      |
| Job queue                  | Custom (via API/CLI)                | Built-in                            |
| Web UI                     | Custom (optional)                   | Built-in                            |
| Emulator binary control    | Full control, custom images         | Limited to supported images         |
| Architecture support       | x86, ARM, IA-64 (flexible)          | x86/x86_64                          |
| Open source                | Yes                                 | Google-managed                      |
| Scripting/automation       | Highly scriptable                   | Out-of-the-box integration          |

- **ATS strengths:** Multi-devkit support, job queue, web UI, easy setup
- **QEMU farm strengths:** Full emulator control, flexible image support, open-source, easier scripting
- **Gaps & Recommendations:** Identify which features are essential for your use case and where custom development is justified

---

### **7. Next Steps & Questions**

- Is your server running Linux with nested VT-x/KVM enabled?
- Do you prefer Docker-based containers or direct QEMU processes?
- Once your environment is confirmed, begin with the single-emulator headless prototype and iterate from there.



# Roadmap

Here's a high‑level roadmap for standing up a QEMU‑based, multi‑tenant Android emulator farm, automating app installs/tests, and then comparing it to Google’s ATS. Let me know if this fits your needs or if you’d like to tweak anything before we dive into implementation:

1. Environment & Prerequisites
   ```bash
   # (On Linux server) install QEMU/KVM, Docker, Android SDK tools
   sudo apt-get update && sudo apt-get install -y qemu-kvm docker.io
   ```
2. Prototype single headless emulator
   ```bash
   cd QEMU/docker
   docker compose build
   docker compose up -d
   ```
3. Verify API & emulator
   ```bash
   docker compose ps
   curl -X POST http://localhost:5001/emulators
   docker ps -a
   docker logs <emu_container_id>
   ```
4. Scale to N instances (via API calls)
5. CI/Test automation & results collection
6. Compare with Google's ATS

## Regarding installing QEMU

If you’re on:
- Linux, install qemu-kvm (and enable nested VT-x).
- Mac, Docker Desktop includes a QEMU binary for containers; no host install is needed unless you run emulators locally outside containers.

## Completed Steps

- Created Dockerfiles for `emulator` (Ubuntu + Android SDK + QEMU) and `api` (Flask service).
- Configured `docker-compose.yml` and built images:
  ```bash
  docker compose up --build -d
  ```
- Confirmed running containers:
  ```bash
  docker compose ps
  # qemu-api-1  Up 5001/tcp
  # qemu-emulator-*  Up (unhealthy until emulator boots)
  ```
- Spun up a new emulator via API:
  ```bash
  curl -s -X POST http://localhost:5001/emulators
  # {"id":"...","ports":{...}}
  ```
- Install ADB:
  - Linux:
    ```bash
    sudo apt-get install -y adb
    ```
  - Mac:
    ```bash
    brew install android-platform-tools
    ```
  - Windows:
    ```powershell
    choco install android-sdk
    ```

- Connect to ADB:
  ```bash
  adb connect localhost:<mapped_port>
  ```

The `<mapped_ports>` are simply the host-side TCP ports that Docker has bound to the emulator's internal ports (5554 for console, 5555 for ADB). You can see them in two ways:

Via the API JSON you got back when you did
```bash
curl -s -X POST http://localhost:5001/emulators
```
Example response:
```json
{
  "id":"13ca2ba0-6b4f-46ce-839e-94bda2be86d3",
  "ports":{
    "5554/tcp":[{"HostIp":"0.0.0.0","HostPort":"32768"}],
    "5555/tcp":[{"HostIp":"0.0.0.0","HostPort":"32769"}]
  }
}
```
Here your mapped ports are 32768 (console) and 32769 (ADB). To connect via ADB you'd run:
```bash
adb connect localhost:32769
```
Or by inspecting the container directly:
```bash
docker ps                   # find your emu_<id> container name
docker port emu_<id> 5555   # prints the HostPort for container’s 5555/tcp
```
You can replace `<mapped_port>` with whatever HostPort you see under "5555/tcp" (that's the ADB port).

When you see your emulator in the “offline” state it simply means the Android runtime hasn’t finished booting yet—ADB will connect its socket, but the guest OS isn’t ready to talk.

Here’s what to do next:

1. Wait for the emulator to boot
Run:
```bash
adb -s localhost:59705 wait-for-device
adb -s localhost:59705 shell getprop sys.boot_completed
```
Keep re‑running the getprop command until it prints 1. Once boot is complete, adb devices will list it as “device” instead of “offline.”

2. Monitor emulator logs
In another terminal:
```bash
docker logs emu_8f5283a3-7c7c-41d6-8c33-83474cf9bee8 -f
```
Watch for a line like
```bash
boot completed
```
That tells you the guest is up.
3. Automate boot-wait in your API (optional)
If you’d rather have your Flask endpoint only return once the emulator is fully up, you can extend your polling loop to inspect logs for “boot completed” before returning the port mapping.
Once the guest is up, you can proceed:

```bash
adb -s localhost:59705 install path/to/your.apk
adb -s localhost:59705 shell am instrument -w com.example.test/androidx.test.runner.AndroidJUnitRunner
adb -s localhost:59705 pull /sdcard/results.xml ./results.xml
```


Do you have the host QEMU installed? See Notes.md for details.

## Cleaning up docker
```bash
docker system prune -af
```  