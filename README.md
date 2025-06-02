# Q - Project: Android Emulator Management System

A streamlined and scalable system for managing Android emulators in Docker containers, accessible via a REST API and a web-based console. This QEMU-based multi-tenant Android emulator farm allows you to launch multiple headless Android emulators, connect via ADB, install APKs, run tests, and collect results programmatically.

## System Architecture

This project implements a multi-tier architecture:

1.  **Emulator Containers**: Docker containers running Ubuntu, configured with the Android SDK and QEMU. Each container runs an Android system image (e.g., x86 API 30/Android 11) in headless mode.
      * Exposed ports per emulator instance typically include:
          * Emulator console (e.g., 5554)
          * Emulator ADB (e.g., 5555)
          * Container's ADB server (e.g., 5037 - though the web console might manage distinct server ports for host ADB interaction)
2.  **API Service (Backend)**: A REST API (typically running on port `5001`) built with Flask (or similar) that manages the lifecycle of emulator containers. It handles creation, listing, deletion, and port assignment.
3.  **Web Console (Frontend)**: A user-friendly web interface (typically running on port `5000`) for interacting with the API, allowing users to manage emulators, connect via ADB, install APKs, access telnet consoles, and perform other administrative tasks.

## Prerequisites

  * **Operating System**:
      * Linux host with KVM nested virtualization (Recommended for optimal performance).
      * macOS with Docker Desktop.
      * Windows with Docker Desktop (ensure WSL 2 backend is used).
  * **Docker & Docker Compose**: Docker Compose v2+ is required.
  * **Android Debug Bridge (adb)**: (Optional, but highly recommended for direct interaction)
      * **Windows**:
        ```powershell
        choco install android-sdk # or
        choco install android-sdk-platform-tools-common
        ```
      * **macOS**:
        ```bash
        brew install android-platform-tools
        ```
      * **Linux**:
        ```bash
        sudo apt update && sudo apt install adb
        ```
  * **jq (for command-line JSON parsing)**:
      * **Windows**:
        ```powershell
        choco install jq -y
        ```
      * **macOS**:
        ```bash
        brew install jq
        ```
      * **Linux**:
        ```bash
        sudo apt update && sudo apt install jq
        ```
  * **Git**: For cloning the repository.

## Quick Start

1.  **Clone the Repository**:

    ```bash
    git clone <your_repository_url_or_path_to_project>
    cd <project_directory_name> # e.g., QEMU or AndroidEmulatorManagementSystem
    ```

2.  **Start Services with Docker Compose**:
    This command will build the necessary Docker images (if not already built) and start all defined services (emulator containers, API, web console) in detached mode.

    ```bash
    docker-compose up --build -d
    ```

    To start without detached mode (to see logs directly in the terminal):

    ```bash
    docker-compose up --build
    ```

    If you just want to start pre-built services:

    ```bash
    docker-compose up
    ```

3.  **Verify Services**:
    Check the status of your running containers:

    ```bash
    docker-compose ps
    ```

    You should see services like `qemu-emulator-1` (or similar for emulator instances), `qemu-api-1` (or `api-service`), and potentially a `web-console` service, listed as `Up` or `Up (healthy)`.

4.  **Accessing the System**:

      * **Web Console**: Open your browser and navigate to `http://localhost:5000`
      * **API (Directly)**: You can interact with the API endpoints, for example, to list emulators: `http://localhost:5001/emulators`

## Key Features

  * Dynamic creation and management of multiple Android emulators.
  * Headless emulator operation, optimized for server environments.
  * RESTful API for programmatic control and integration.
  * User-friendly web console for manual management.
  * Connection to emulators via Android Debug Bridge (ADB).
  * APK installation to connected devices.
  * Telnet access to emulator consoles for low-level control.
  * Tools for managing ADB server instances and Docker containers (e.g., "Kill ADB Server", "Remove Docker containers" via the web console).

## API Endpoints

The API service (running on `http://localhost:5001` by default) provides the following primary endpoints:

| Endpoint          | Method | Description                                  |
| :---------------- | :----- | :------------------------------------------- |
| `/emulators`      | GET    | List all active emulator sessions/instances. |
| `/emulators`      | POST   | Create a new emulator session/instance.      |
| `/emulators/{id}` | DELETE | Delete a specific emulator session/instance. |

**Example API Interactions (using `curl` and `jq`):**

  * **Create a new emulator session**:

    ```bash
    curl -s -X POST http://localhost:5001/emulators | jq .
    ```

    For PowerShell users:

    ```powershell
    Invoke-WebRequest -Method Post -Uri http://localhost:5001/emulators | Select-Object -ExpandProperty Content | ConvertFrom-Json # or | jq . if you prefer jq
    ```

    *Expected Response (structure may vary slightly based on your specific API implementation)*:

    ```json
    {
      "id": "unique_session_id_123",
      "status": "creating/running",
      "ports": {
        "console": "host_port_for_5554", // e.g., 32770
        "adb": "host_port_for_5555",     // e.g., 32771
        "adb_server_container": "host_port_for_5037" // Port for the container's internal ADB server
      },
      "adb_connection_string": "emulator-xxxx" // e.g., emulator-5554 if using default console port mapping for ID
    }
    ```

    *(The actual `id` and `HostPort` values will be dynamically assigned by Docker and your API).*

  * **List all emulator sessions**:

    ```bash
    curl http://localhost:5001/emulators | jq .
    ```

    For PowerShell users:

    ```powershell
    Invoke-WebRequest -Uri http://localhost:5001/emulators | Select-Object -ExpandProperty Content | ConvertFrom-Json # or | jq .
    ```

  * **Delete an emulator session** (replace `<SESSION_ID>` with the actual ID from the create/list response):

    ```bash
    curl -X DELETE http://localhost:5001/emulators/<SESSION_ID>
    ```

    For PowerShell users:

    ```powershell
    Invoke-WebRequest -Method Delete -Uri "http://localhost:5001/emulators/<SESSION_ID>"
    ```

## Connecting to Emulators via ADB

Once an emulator is created (either via API or web console), you'll receive port information. Let's assume the API response gave you `<PORT_5555>` as the host port mapped to the emulator's internal ADB port (5555/tcp), and `<PORT_5037>` as the host port mapped to the container's ADB server port (5037/tcp).

You have a few ways to connect:

1.  **Directly to the Emulator's ADB Port**:
    This is often the simplest method if the host port for the emulator's ADB service (5555) is exposed.

    ```bash
    adb connect localhost:<PORT_5555_FROM_API_RESPONSE>
    # Example: adb connect localhost:32771
    adb devices
    ```

2.  **Using the Container's ADB Server Port**:
    This method tells your local ADB client to talk to the ADB server running *inside* the Docker container.

    ```bash
    # For Linux/macOS
    export ADB_SERVER_SOCKET=tcp:localhost:<PORT_5037_FROM_API_RESPONSE>
    adb kill-server
    adb start-server
    adb devices

    # For PowerShell on Windows
    $env:ANDROID_ADB_SERVER_PORT = "<PORT_5037_FROM_API_RESPONSE>" # Or the specific port assigned by your web console/API for host ADB redirection
    adb kill-server
    adb -P $env:ANDROID_ADB_SERVER_PORT start-server
    adb devices
    ```

    *Note: The Web Console might abstract this by assigning unique host ports for different ADB server instances. Refer to the web console's instructions or the API response for the correct port to use with `$env:ANDROID_ADB_SERVER_PORT` or `adb -P <port> start-server`.*

3.  **Using the Web Console's ADB Management**:
    The web console may provide features to manage ADB connections, potentially simplifying the port configuration. Check the UI for options like "Connect ADB" or ADB port information.

## Emulator Boot & Testing Workflow

1.  **Wait for Emulator to Boot Completely**:
    Replace `localhost:<PORT_5555_FROM_API_RESPONSE>` or `emulator-xxxx` (device serial from `adb devices`) with your specific emulator identifier.

    ```bash
    adb -s <emulator_identifier> wait-for-device
    until [ "$(adb -s <emulator_identifier> shell getprop sys.boot_completed)" = "1" ]; do
      echo "Waiting for boot..."
      sleep 1
    done
    echo "Emulator booted successfully!"
    ```

2.  **Install an APK**:

    ```bash
    adb -s <emulator_identifier> install path/to/your/app.apk
    # To reinstall an existing app:
    adb -s <emulator_identifier> install -r path/to/your/app.apk
    ```

3.  **Run Tests (Example)**:
    This depends on your test runner setup.

    ```bash
    adb -s <emulator_identifier> shell am instrument -w <your.test.package/your.TestRunnerClass>
    ```

4.  **Pull Results (Example)**:

    ```bash
    adb -s <emulator_identifier> pull /sdcard/results.xml ./local_results_directory/
    ```

## Command-Line Alternative / Scripts

For command-line users, a PowerShell script might be included for tasks like switching ADB server ports (useful if you are managing multiple local ADB server instances or connecting to emulators that require specific ADB server ports).

```powershell
# Example usage if a script is provided in your project structure
./scripts/adb_switcher.ps1 -port <TARGET_ADB_PORT>
```

Refer to the script's content or accompanying documentation for its specific usage.

## Troubleshooting

  * **Port Conflicts**: Emulator ports are typically assigned dynamically by Docker from a range. If you encounter port conflicts with other services on your host:
      * Stop the conflicting service.
      * Restart the emulator management system (`docker-compose down && docker-compose up`). Docker should assign new ports.
      * Check your `docker-compose.yml` for any fixed port mappings that might be causing issues.
  * **ADB Connection Issues**:
      * Ensure the emulator container is running and healthy (`docker-compose ps`).
      * Use the "Kill ADB Server" feature in the web console or run `adb kill-server` in your terminal, then try reconnecting using the appropriate method (direct port or container ADB server port).
      * Verify you are using the correct host port provided by the API or web console.
      * Check host firewall settings that might be blocking connections to the exposed Docker ports.
      * If using `scrcpy` or other GUI forwarding tools and encountering "Server connection failed," this may indicate issues with the screen-casting server within the emulator, network configuration inside the container, or compatibility. Further debugging for that specific tool is needed.
  * **Performance**: Running many concurrent emulators can be resource-intensive.
      * Reduce the number of concurrently running emulators.
      * Ensure your host machine has sufficient RAM, CPU cores, and fast storage.
      * If on Linux, ensure KVM is enabled and being utilized for better performance.
  * **Emulator Not Booting/Stuck**:
      * Check container logs: `docker-compose logs <emulator_service_name>` (e.g., `docker-compose logs qemu-emulator-1`).
      * Ensure the Android system image is compatible with the QEMU setup.
  * **GUI Access**: By default, these are headless emulators.
      * For GUI, investigate setting up X11 forwarding if your Docker environment supports it.
      * Alternatively, tools like `scrcpy` can be used to mirror the screen, but require a working ADB connection and successful server component startup on the emulator (see ADB connection issues if `scrcpy` fails).

## Running with Vagrant + KVM (Recommended for Linux Users)

For a consistent and optimized environment, especially on Linux, a `Vagrantfile` may be provided to set up a Linux VM (e.g., Ubuntu 20.04) with KVM, Docker, and Docker Compose pre-installed. This automates the setup of the host environment for the emulator farm.

### Vagrant Prerequisites

  * Host machine with KVM support (typically Linux).
  * Vagrant installed.
  * Vagrant Libvirt Provider plugin (if using Libvirt for KVM):
    ```bash
    vagrant plugin install vagrant-libvirt
    ```

### Vagrant Usage

1.  **Navigate to the directory containing the `Vagrantfile`** (usually the project root).

2.  **Start and Provision the VM**:

    ```bash
    vagrant up
    ```

    This will:

      * Download the specified Linux distribution image (if not already cached).
      * Boot the VM.
      * Install Docker, Docker Compose, and other dependencies inside the VM.
      * Automatically clone the project (if configured in Vagrantfile) and run `docker-compose up` to start the emulator farm services inside the VM.
      * Forward necessary ports (e.g., 5000 for web console, 5001 for API, and potentially emulator ADB/console ports) from the VM to your host machine.

3.  **Access Services**: Once `vagrant up` completes, you can access the web console and API via `localhost` on your host machine, as the ports are forwarded.

4.  **SSH into the VM (Optional)**:

    ```bash
    vagrant ssh
    ```

    Inside the VM, you can directly manage Docker containers and view logs.

### Vagrant VM Cleanup

  * **Stop and Destroy the VM**:
    ```bash
    vagrant destroy -f
    ```
    This will shut down and remove the virtual machine and all its associated resources.

## Cleanup (Docker)

To stop and remove all containers, networks, and volumes created by `docker-compose`:

```bash
docker-compose down --volumes
```

To perform a more thorough Docker system cleanup (removes all stopped containers, all unused networks, all dangling images, and all build cache):

```bash
docker system prune -af
```

**Caution**: `docker system prune -af` is aggressive and will remove any unused Docker resources, not just those related to this project.

## License

MIT (or specify the license used by your project).