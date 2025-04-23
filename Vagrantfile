# Vagrantfile for QEMU Android Emulator Farm with KVM

Vagrant.configure("2") do |config|
  # Base box
  config.vm.box = "ubuntu/focal64"

  # Forward emulator and API ports to host
  config.vm.network "forwarded_port", guest: 5554, host: 5554
  config.vm.network "forwarded_port", guest: 5555, host: 5555
  config.vm.network "forwarded_port", guest: 5037, host: 5037
  config.vm.network "forwarded_port", guest: 5001, host: 5001

  # Use libvirt provider for KVM nested virtualization
  config.vm.provider "libvirt" do |lv|
    lv.cpu_mode = 'host-passthrough'
    lv.nested = true
    lv.cpus = 4
    lv.memory = 8192
  end

  # Sync project directory into the VM
  config.vm.synced_folder ".", "/home/vagrant/QEMU"

  # Check for KVM support before provisioning
  config.vm.provision "shell", run: "always", inline: <<-SHELL
    echo "Checking for KVM support..."
    if ! grep -E -q '(vmx|svm)' /proc/cpuinfo || [ ! -e /dev/kvm ]; then
      echo "ERROR: Host KVM not available. Please ensure virtualization is enabled in your BIOS and KVM is properly set up."
      exit 1
    else
      echo "KVM support detected. Proceeding with setup..."
    fi
  SHELL

  # Provision VM: install dependencies and start emulator farm
  config.vm.provision "shell", inline: <<-SHELL
    # Update and install packages
    sudo apt-get update
    sudo apt-get install -y docker.io qemu-kvm libvirt-daemon-system curl

    # Install Docker Compose v2
    sudo apt-get install -y python3-pip
    sudo pip3 install docker-compose

    # Add vagrant user to docker group
    sudo usermod -aG docker vagrant
    sudo usermod -aG libvirt vagrant
    sudo usermod -aG kvm vagrant

    # Make sure the services are running
    sudo systemctl enable docker.service
    sudo systemctl start docker.service
    sudo systemctl enable libvirtd.service
    sudo systemctl start libvirtd.service

    # Build and start the emulator farm
    cd /home/vagrant/QEMU
    echo "Starting Docker services..."
    sudo -u vagrant docker-compose up --build -d

    echo "Waiting for services to initialize..."
    sleep 10

    # Check if services are running
    if sudo -u vagrant docker-compose ps | grep -q "Up"; then
      echo "Emulator farm is now running!"
      echo "API available at: http://localhost:5001"
      echo "Connect to emulator via: adb connect localhost:5555"
    else
      echo "Warning: Services may not have started correctly. Check with 'docker-compose ps'"
    fi
  SHELL
end