## Q - Project: Android Emulator Management System Documentation

This document outlines the functionality and current status of the Q - Project: Android Emulator Management System, which leverages QEMU and Docker to provide on-demand Android emulators.

### System Overview

The Q - Project: Android Emulator Management System is designed to create, manage, and delete containerized Android emulators. It features a three-tier architecture:

1.  **Emulator Containers**: Ubuntu 22.04 based Docker containers running QEMU Android emulators (currently Android 11). These containers expose console and ADB ports and support SwiftShader for GPU acceleration.
2.  **REST API Service (Port 5001)**: Manages the lifecycle of emulator containers, including creation, listing, deletion, and port assignment for console and ADB. It interacts with Docker and generates unique device IDs.
3.  **Web Console (Port 5000)**: A user-friendly interface for managing emulators, allowing creation, deletion, ADB connection management, APK installation, and telnet console access. It also includes tools for managing ADB servers and Docker containers.

### Key Features

  * Dynamic creation of Android emulators with unique device IDs.
  * Automatic port allocation for console (e.g., 5334) and ADB (e.g., 8948, 9226) connections.
  * ADB connection management for installing applications and debugging.
  * Telnet console access for low-level emulator control.
  * Docker containerization for isolation and resource management.
  * Web-based interface for simplified management.
  * RESTful API for programmatic control and integration.

### Emulator Interaction and Application Installation

Users can interact with the emulators primarily through Android Debug Bridge (ADB). The system allows for specific ADB server ports to be assigned to different emulator instances.

**Connecting to an Emulator via ADB:**

1.  **Initial State:** By default, `adb devices` may not show any connected emulators.
    ```powershell
    PS D:\Project\QEMU> adb devices
    List of devices attached
    ```
2.  **Assigning a Specific ADB Server Port:** To connect to a specific emulator instance, the ADB server port environment variable needs to be set, and the ADB server restarted on that port.
      * **Example for emulator-5334 (hypothetical console port):**
        ```powershell
        PS D:\Project\QEMU> adb kill-server
        PS D:\Project\QEMU> $env:ANDROID_ADB_SERVER_PORT = "8948"
        PS D:\Project\QEMU> adb -P 8948 start-server
        PS D:\Project\QEMU> adb devices
        List of devices attached
        emulator-5334   device
        ```
      * **Example for emulator-6376 (hypothetical console port):**
        ```powershell
        PS D:\Project\QEMU> adb kill-server
        PS D:\Project\QEMU> $env:ANDROID_ADB_SERVER_PORT = "9226"
        PS D:\Project\QEMU> adb -P 9226 start-server
        PS D:\Project\QEMU> adb devices
        List of devices attached
        emulator-6376   device
        ```
3.  **Verifying Emulator Properties:** Once connected, ADB commands can be used to interact with the emulator. For instance, to get the CPU ABI list:
    ```powershell
    PS D:\Project\QEMU> adb shell getprop ro.product.cpu.abilist
    >>
    x86,armeabi-v7a,armeabi
    ```
    The logs indicate the emulator is running Android 11 ("current version is \#30", "[server] INFO: Device: [Google] google sdk\_gphone\_x86 (Android 11)").

**Installing an APK:**

After successfully connecting to an emulator via a specific ADB port, applications (APKs) can be installed using the `adb install` command. The `-r` flag allows for reinstalling an existing application.

```powershell
PS D:\Project\QEMU> $env:ANDROID_ADB_SERVER_PORT = "9226"
PS D:\Project\QEMU> adb -P 9226 start-server
PS D:\Project\QEMU> adb devices
List of devices attached
emulator-6376   device

PS D:\Project\QEMU> adb install -r d:\Project\QEMU\app-debug.apk
Performing Streamed Install
Success
```

This confirms that the APK was successfully installed on `emulator-6376`.

### GUI Forwarding and Screen Mirroring

A significant challenge identified is the lack of direct GUI forwarding from the containerized emulators. The emulators run headlessly by default.

**Current Status:**

  * APKs can be installed via ADB, and the device is listed, confirming the emulator is running.
  * Attempts to use `scrcpy` (Screen Copy) to mirror the emulator's screen have been made. `scrcpy` detects the ADB device (e.g., `emulator-6376`).
    ```powershell
    ./scrcpy.exe -V debug
    scrcpy 3.2 <https://github.com/Genymobile/scrcpy>
    INFO: ADB device found:
    INFO:     --> (tcpip)  emulator-6376            device  sdk_gphone_x86
    ...
    [server] INFO: Device: [Google] google sdk_gphone_x86 (Android 11)
    ...
    ERROR: Server connection failed
    ```
    Despite detecting the device and pushing the `scrcpy-server` successfully, the connection ultimately fails. This occurs even when attempting to run `scrcpy` with reduced resolution and no audio (`./scrcpy.exe -m 1024 --no-audio`).
  * Basic ADB shell access to the emulator is functional:
    ```powershell
    PS C:\scrcpy> adb -s emulator-6376 shell
    generic_x86_arm:/ $ exit
    ```
  * The available AVD (Android Virtual Device) is listed as `Pixel_8_Pro_API_35`.

**Potential Solutions for GUI Access:**

1.  **X11 Forwarding:** If the Docker container environment supports X11 forwarding, configure it with the appropriate `DISPLAY` environment variable to show the emulator window on the host desktop. This is a common approach with solutions like `dock-droid`.
2.  **`scrcpy` (Further Investigation):** While initial attempts failed, `scrcpy` remains a viable option. The "ERROR: Server connection failed" suggests issues that could be related to network configuration within the container, firewall settings, or specific emulator compatibility issues with the `scrcpy` server component on Android 11 x86. Further debugging of `scrcpy` connectivity is needed. The tool can be downloaded from `https://github.com/Genymobile/scrcpy/releases`.
3.  **Local Android SDK AVD:** If a local Android SDK and AVD are available, the emulator GUI can be started directly using the `emulator -avd <name>` command (e.g., `emulator -avd Pixel_8_Pro_API_35`). This is more for local development/testing rather than the containerized system's primary use case but can be a fallback for GUI interaction.
4.  **WebRTC-based Screen Sharing:** As noted in future expansion, implementing WebRTC could provide direct screen interaction through the browser.

### Technical Challenges Overcome

  * Configured proper GPU acceleration (SwiftShader) for Android emulators in containers.
  * Implemented dynamic port allocation to avoid conflicts.
  * Created a robust ADB connection management system.
  * Ensured proper container lifecycle management.
  * Developed an intuitive user interface for emulator control.
  * Established reliable communication between the web app and API.
  * Handled proper cleanup of resources when deleting emulators.

### Benefits of the Solution

  * **Scalability**: Easily scale up to run multiple emulators.
  * **Resource Efficiency**: Containers provide isolation with minimal overhead.
  * **Accessibility**: Web interface simplifies emulator access.
  * **Automation**: API enables integration with CI/CD pipelines.
  * **Flexibility**: Potential to support different Android versions and configurations.
  * **Maintainability**: Containerized architecture simplifies deployment.

-----

### FEAT - System Status and Next Steps

**Done:**

  * **FEAT-001-EmulatorContainerization**: Successfully containerized Android (Android 11, x86 ABI) emulators using QEMU and Docker.
  * **FEAT-002-RestAPILifecycleManagement**: Implemented a REST API for creating, listing, and deleting emulator instances.
  * **FEAT-003-WebConsoleInterface**: Developed a web console for user interaction with the emulator management system.
  * **FEAT-004-DynamicPortAllocation**: Enabled automatic and unique port assignment for ADB and console access per emulator.
  * **FEAT-005-ADBManagement**: Established procedures for connecting to emulators via specific ADB server ports.
  * **FEAT-006-APKInstallation**: Successfully demonstrated APK installation onto running emulators via ADB.


**Planned Next:**
  * **FEAT-007-CombineAPIInstances**: Currently, two flask apis are exising. Unify them. /docker/api/app.py and /web-app/app.py
  * **FEAT-008-BasicEmulatorInteraction**: Confirmed ability to execute basic ADB shell commands on emulators.
  * **FEAT-009-InvestigateScrcpyFailure**: Diagnose and resolve the "Server connection failed" error when using `scrcpy` to enable screen mirroring for headless emulators.
  * **FEAT-010-ImplementX11Forwarding**: Explore and implement X11 forwarding for Docker containers to provide direct GUI output from emulators if `scrcpy` proves unsuitable or as an alternative.
  * **FEAT-011-SupportAdditionalAVDs**: Expand support to include and manage different Android versions and device profiles (e.g., Pixel\_8\_Pro\_API\_35).
  * **FEAT-012-EnhancedMonitoring**: Develop and integrate enhanced monitoring and resource usage statistics for emulators and the host system.
  * **FEAT-013-TestAutomationFrameworkIntegration**: Design and implement integration points for popular test automation frameworks.
  * **FEAT-014-PerformanceOptimization**: Conduct performance analysis and optimization to support a higher number of concurrent emulators.


