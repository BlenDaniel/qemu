# ADB Server Manager Script
# This script helps manage and switch between different ADB server instances

function Show-Menu {
    Clear-Host
    Write-Host "===== ADB Server Manager =====" -ForegroundColor Cyan
    Write-Host "1. List Available Devices"
    Write-Host "2. Kill Current ADB Server"
    Write-Host "3. Start ADB Server with Default Port"
    Write-Host "4. Create New Emulator and Connect"
    Write-Host "5. Connect to Specific Emulator"
    Write-Host "6. View Current ADB Port Configuration"
    Write-Host "7. List All Running Emulators"
    Write-Host "8. Delete Emulator"
    Write-Host "9. Exit"
    Write-Host "============================" -ForegroundColor Cyan
}

function List-Devices {
    Write-Host "`nListing Available Devices..." -ForegroundColor Yellow
    $currentPort = Get-CurrentAdbPort
    Write-Host "Current ADB server port: $currentPort" -ForegroundColor Gray
    
    $devicesOutput = adb devices
    Write-Host $devicesOutput
    
    if ($devicesOutput -match "cannot connect to daemon") {
        Write-Host "ADB server is not running or not accessible." -ForegroundColor Red
    }
    
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Kill-AdbServer {
    Write-Host "`nKilling ADB Server..." -ForegroundColor Yellow
    
    # First try normal kill
    adb kill-server
    
    # Force kill any remaining ADB processes
    $adbProcesses = Get-Process -Name "adb" -ErrorAction SilentlyContinue
    if ($adbProcesses) {
        Write-Host "Force killing remaining ADB processes..." -ForegroundColor Yellow
        Stop-Process -Name "adb" -Force
    }
    
    Write-Host "ADB Server killed successfully." -ForegroundColor Green
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Start-DefaultAdbServer {
    Write-Host "`nStarting ADB Server with default port (5037)..." -ForegroundColor Yellow
    
    # Clear any custom port environment variable
    $env:ANDROID_ADB_SERVER_PORT = $null
    
    # Start the ADB server
    adb start-server
    
    Write-Host "ADB Server started on default port." -ForegroundColor Green
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Create-NewEmulator {
    Write-Host "`nCreating New Emulator via API..." -ForegroundColor Yellow
    
    # Get Android version selection
    Write-Host "`nSelect Android Version:" -ForegroundColor Cyan
    Write-Host "1. Android 11"
    Write-Host "2. Android 14"
    $versionChoice = Read-Host "Enter choice (1-2, default: 1)"
    
    $androidVersion = "11"
    switch ($versionChoice) {
        "2" { $androidVersion = "14" }
        default { $androidVersion = "11" }
    }
    
    Write-Host "Selected: Android $androidVersion" -ForegroundColor Green
    
    $apiUrl = Read-Host "Enter API URL (default: http://localhost:5001/api/emulators)"
    if ([string]::IsNullOrWhiteSpace($apiUrl)) {
        $apiUrl = "http://localhost:5001/api/emulators"
    }
    
    # Prepare request body
    $requestBody = @{
        android_version = $androidVersion
        map_adb_server = $true
    } | ConvertTo-Json
    
    try {
        Write-Host "`nSending request to create Android $androidVersion emulator..." -ForegroundColor Yellow
        
        $response = Invoke-WebRequest -Method Post -Uri $apiUrl -Body $requestBody -ContentType "application/json"
        $emulatorInfo = $response.Content | ConvertFrom-Json
        
        Write-Host "`n✓ New Android $androidVersion Emulator Created!" -ForegroundColor Green
        Write-Host "================================" -ForegroundColor Cyan
        Write-Host "Device ID: $($emulatorInfo.device_id)" -ForegroundColor White
        Write-Host "Android Version: $($emulatorInfo.android_version)" -ForegroundColor White
        Write-Host "ADB Port: $($emulatorInfo.ports.adb)" -ForegroundColor White
        Write-Host "ADB Server Port: $($emulatorInfo.ports.adb_server)" -ForegroundColor White
        Write-Host "Console Port: $($emulatorInfo.ports.console)" -ForegroundColor White
        Write-Host "================================" -ForegroundColor Cyan
        
        # Display ADB commands for reference
        Write-Host "`nADB Commands for this emulator:" -ForegroundColor Yellow
        Write-Host "Windows: `$env:ANDROID_ADB_SERVER_PORT = `"$($emulatorInfo.ports.adb_server)`"" -ForegroundColor Gray
        Write-Host "Unix/Mac: export ANDROID_ADB_SERVER_PORT=$($emulatorInfo.ports.adb_server)" -ForegroundColor Gray
        Write-Host "Connect: adb connect localhost:$($emulatorInfo.ports.adb)" -ForegroundColor Gray
        Write-Host "Console: telnet localhost $($emulatorInfo.ports.console)" -ForegroundColor Gray
        
        # Automatic setup
        Write-Host "`nSetting up connection with the new ADB server..." -ForegroundColor Yellow
        
        # Set the environment variable
        $serverPort = $emulatorInfo.ports.adb_server
        $env:ANDROID_ADB_SERVER_PORT = $serverPort
        Write-Host "✓ Set ANDROID_ADB_SERVER_PORT = $serverPort" -ForegroundColor Green
        
        # Kill any existing ADB server
        adb kill-server
        Write-Host "✓ Killed existing ADB server" -ForegroundColor Green
        
        # Start the ADB server with the provided port
        Write-Host "✓ Starting ADB server with port $serverPort" -ForegroundColor Green
        adb -P $serverPort start-server
        
        # Wait a moment for server to start
        Start-Sleep -Seconds 2
        
        # Connect to the emulator
        Write-Host "✓ Connecting to emulator at port $($emulatorInfo.ports.adb)" -ForegroundColor Green
        adb connect localhost:$($emulatorInfo.ports.adb)
        
        # Check final status
        Write-Host "`nFinal Status Check:" -ForegroundColor Yellow
        $finalDevices = adb devices
        Write-Host $finalDevices
        
        if ($emulatorInfo.adb_setup.final_device_status -eq "device") {
            Write-Host "`n🎉 Emulator is ready and connected!" -ForegroundColor Green
        } else {
            Write-Host "`n⚠️  Emulator created but may still be starting up..." -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "`n❌ Error creating emulator: $_" -ForegroundColor Red
    }
    
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Connect-ToEmulator {
    Write-Host "`nConnect to Specific Emulator..." -ForegroundColor Yellow
    
    $emulatorPort = Read-Host "Enter emulator port (e.g., 5394)"
    
    if ($emulatorPort -notmatch "^\d+$") {
        Write-Host "Invalid port number! Please enter a valid number." -ForegroundColor Red
        Write-Host "`nPress any key to continue..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        return
    }
    
    adb connect localhost:$emulatorPort
    
    Write-Host "Connection attempt completed." -ForegroundColor Green
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Get-CurrentAdbPort {
    $port = $env:ANDROID_ADB_SERVER_PORT
    if ([string]::IsNullOrWhiteSpace($port)) {
        return "5037 (default)"
    }
    return $port
}

function Show-CurrentConfig {
    Write-Host "`nCurrent ADB Configuration" -ForegroundColor Cyan
    Write-Host "=========================" -ForegroundColor Cyan
    
    $currentPort = Get-CurrentAdbPort
    Write-Host "ADB Server Port: $currentPort" -ForegroundColor Yellow
    
    # Check if ADB server is running
    $serverStatus = adb devices
    if ($serverStatus -match "daemon started successfully" -or $serverStatus -match "List of devices attached") {
        Write-Host "ADB Server Status: Running" -ForegroundColor Green
    } else {
        Write-Host "ADB Server Status: Not running or inaccessible" -ForegroundColor Red
    }
    
    # List connected devices
    Write-Host "`nConnected Devices:" -ForegroundColor Yellow
    $devicesOutput = adb devices
    $deviceLines = $devicesOutput -split "`n" | Select-Object -Skip 1
    
    $foundDevices = $false
    foreach ($line in $deviceLines) {
        if ($line.Trim() -ne "") {
            Write-Host $line -ForegroundColor White
            $foundDevices = $true
        }
    }
    
    if (-not $foundDevices) {
        Write-Host "No devices connected" -ForegroundColor Gray
    }
    
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function List-RunningEmulators {
    Write-Host "`nListing All Running Emulators..." -ForegroundColor Yellow
    
    $apiUrl = Read-Host "Enter API URL (default: http://localhost:5001/api/emulators)"
    if ([string]::IsNullOrWhiteSpace($apiUrl)) {
        $apiUrl = "http://localhost:5001/api/emulators"
    }
    
    try {
        $response = Invoke-WebRequest -Method Get -Uri $apiUrl
        $emulators = $response.Content | ConvertFrom-Json
        
        if ($emulators.PSObject.Properties.Count -eq 0) {
            Write-Host "No emulators are currently running." -ForegroundColor Gray
        } else {
            Write-Host "`nRunning Emulators:" -ForegroundColor Cyan
            Write-Host "==================" -ForegroundColor Cyan
            
            foreach ($emulatorId in $emulators.PSObject.Properties.Name) {
                $emulator = $emulators.$emulatorId
                Write-Host "`nEmulator ID: $emulatorId" -ForegroundColor Yellow
                Write-Host "  Device ID: $($emulator.device_id)" -ForegroundColor White
                Write-Host "  Android Version: $($emulator.android_version)" -ForegroundColor White
                Write-Host "  Status: $($emulator.status)" -ForegroundColor White
                Write-Host "  ADB Port: $($emulator.ports.adb)" -ForegroundColor White
                Write-Host "  ADB Server Port: $($emulator.ports.adb_server)" -ForegroundColor White
                Write-Host "  Console Port: $($emulator.ports.console)" -ForegroundColor White
            }
        }
    }
    catch {
        Write-Host "❌ Error listing emulators: $_" -ForegroundColor Red
    }
    
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Delete-Emulator {
    Write-Host "`nDelete Emulator..." -ForegroundColor Yellow
    
    # First list available emulators
    $apiUrl = Read-Host "Enter API URL (default: http://localhost:5001/api/emulators)"
    if ([string]::IsNullOrWhiteSpace($apiUrl)) {
        $apiUrl = "http://localhost:5001/api/emulators"
    }
    
    try {
        $response = Invoke-WebRequest -Method Get -Uri $apiUrl
        $emulators = $response.Content | ConvertFrom-Json
        
        if ($emulators.PSObject.Properties.Count -eq 0) {
            Write-Host "No emulators are currently running to delete." -ForegroundColor Gray
            Write-Host "`nPress any key to continue..."
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
            return
        }
        
        Write-Host "`nAvailable Emulators:" -ForegroundColor Cyan
        $emulatorList = @()
        $index = 1
        
        foreach ($emulatorId in $emulators.PSObject.Properties.Name) {
            $emulator = $emulators.$emulatorId
            Write-Host "$index. $($emulator.device_id) (Android $($emulator.android_version)) - $($emulator.status)" -ForegroundColor White
            $emulatorList += @{Index = $index; Id = $emulatorId; Info = $emulator}
            $index++
        }
        
        $choice = Read-Host "`nEnter emulator number to delete (1-$($emulatorList.Count))"
        
        if ($choice -match "^\d+$" -and [int]$choice -ge 1 -and [int]$choice -le $emulatorList.Count) {
            $selectedEmulator = $emulatorList[[int]$choice - 1]
            $emulatorId = $selectedEmulator.Id
            $deviceId = $selectedEmulator.Info.device_id
            
            $confirm = Read-Host "Are you sure you want to delete emulator '$deviceId'? (y/N)"
            if ($confirm -eq "y" -or $confirm -eq "Y") {
                $deleteUrl = "$apiUrl/$emulatorId"
                $deleteResponse = Invoke-WebRequest -Method Delete -Uri $deleteUrl
                
                if ($deleteResponse.StatusCode -eq 204) {
                    Write-Host "✓ Emulator '$deviceId' deleted successfully!" -ForegroundColor Green
                } else {
                    Write-Host "❌ Failed to delete emulator." -ForegroundColor Red
                }
            } else {
                Write-Host "Deletion cancelled." -ForegroundColor Yellow
            }
        } else {
            Write-Host "Invalid selection." -ForegroundColor Red
        }
    }
    catch {
        Write-Host "❌ Error deleting emulator: $_" -ForegroundColor Red
    }
    
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# Main execution loop
do {
    Show-Menu
    $choice = Read-Host "`nEnter your choice"
    
    switch ($choice) {
        "1" { List-Devices }
        "2" { Kill-AdbServer }
        "3" { Start-DefaultAdbServer }
        "4" { Create-NewEmulator }
        "5" { Connect-ToEmulator }
        "6" { Show-CurrentConfig }
        "7" { List-RunningEmulators }
        "8" { Delete-Emulator }
        "9" { return }
        default { 
            Write-Host "`nInvalid choice. Please try again." -ForegroundColor Red
            Write-Host "Press any key to continue..."
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        }
    }
} while ($true)