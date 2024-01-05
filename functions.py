import os
import sys
import platform
import subprocess
import requests
import logging
from logging.handlers import RotatingFileHandler
import itertools
import threading
import time
import configparser

logging.basicConfig(filename='pve-templates.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logHandler = RotatingFileHandler('pve-templates.log', maxBytes=10000000, backupCount=3)
logHandler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

class Spinner:
    def __init__(self, message, success_message="", failure_message="", delay=0.1):
        self.spinner = itertools.cycle(['-', '/', '|', '\\'])
        self.message = message
        self.success_message = success_message
        self.failure_message = failure_message
        self.delay = delay
        self.stop_running = threading.Event()
        self.spin_thread = threading.Thread(target=self.initiate_spin)
        self.success = None

    def initiate_spin(self):
        while not self.stop_running.is_set():
            sys.stdout.write(f"\r{self.message} {next(self.spinner)}")
            sys.stdout.flush()
            time.sleep(self.delay)

    def start(self):
        self.spin_thread.start()

    def stop(self, success=True):
        self.success = success
        self.stop_running.set()
        self.spin_thread.join()
        final_message = self.success_message if success else self.failure_message
        sys.stdout.write('\r' + ' ' * (len(self.message) + 2) + '\r')  # Clear the line
        sys.stdout.write(f"{final_message}\n")
        sys.stdout.flush()

def load_config(config_path='config.ini'):
    config = configparser.ConfigParser()
    config.read(config_path)
    return config

def runas_root():
    if os.geteuid() != 0:
        logging.error("Tried to run as non-root")
        return False
    else:
        logging.info("Running as root")
        return True

def check_os(verbose):
    if 'pve' in platform.platform():
        logging.info("Running on Proxmox VE")
        return True
    else:
        logging.error("Not running on Proxmox VE")
        return False

def run_command(cmd, verbose):
    if verbose:
        subprocess.run(cmd, check=True)
    else:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def check_virt(verbose):
    try:
        run_command(["virt-customize", "--version"], verbose)
        logging.info("virt-customize is installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        if verbose:
            print("\033[31m❌ virt-customize is not installed or not found in PATH\033[0m")
        logging.error("virt-customize is not installed or not found in PATH")
        return False

def check_tqdm(verbose):
    try:
        from tqdm import tqdm
        logging.info("python3-tqdm is installed")
        return True
    
    except ImportError:
        logging.error("python3-tqdm is not installed")
        return False
    
    if verbose:
        if 'tqdm' in sys.modules:
            print("\033[32m✅ python3-tqdm is installed\033[0m")
        else:
            print("\033[31m❌ python3-tqdm is not installed\033[0m")

def install_dependencies(verbose):
    try:
        run_command(["apt", "install", "-y", "python3-tqdm", "libguestfs-tools"], verbose)
        logging.info("Installed dependencies")
        return True
    except subprocess.CalledProcessError:
        logging.error("Failed to install dependencies")
        return False

def check_and_delete_vm(vmid, name, verbose):
    success_message = f"\033[32m✅ Removed template {name} [{vmid}]\033[0m"
    failure_message = f"\033[31m❌ Error while removing template {name} [{vmid}]\033[0m"
    spinner = Spinner(f"Checking if template {name} exists and deleting it if it does", success_message, failure_message)
    spinner.start()
    try:
        run_command(["qm", "status", vmid], verbose)
    except subprocess.CalledProcessError:
        spinner.stop()
        return True

    try:
        run_command(["qm", "destroy", vmid], verbose)
        spinner.stop()
        return True
    except subprocess.CalledProcessError:
        spinner.stop()
        return False
    
def customize_image(temporary_directory, image_name, name, verbose):
    success_message = f"\033[32m✅ Customized image for {name}\033[0m"
    failure_message = f"\033[31m❌ Error while customizing image for {name}\033[0m"
    spinner = Spinner(f"Customizing image for {name}", success_message, failure_message)
    try:
        spinner.start()
        run_command(["virt-customize", "-a", f"{temporary_directory}/{image_name}", "--firstboot-install", "qemu-guest-agent"], verbose)
        logging.info(f"Added qemu-guest-agent installation on first boot in {image_name}")
        run_command(["virt-customize", "-a", f"{temporary_directory}/{image_name}", "--firstboot-command", "systemctl enable --now qemu-guest-agent"], verbose)
        logging.info(f"Enabled qemu-guest-agent on first boot in {image_name}")
    except Exception as e:
        logging.error(f"Failed to customize {image_name}")
        print("ERROR:", e)
    finally:
        spinner.stop()

def create_template(vmid, name, image_name, template_storage, temporary_directory, ssh_keyfile, username, verbose):
    success_message = f"\033[32m✅ Created template {name}\033[0m"
    failure_message = f"\033[31m❌ Error while creating template {name}\033[0m"
    spinner = Spinner(f"Trying to create template {name}", success_message, failure_message)
    try:
        spinner.start()
        commands = [
            ["qm", "create", vmid, "--name", name, "--ostype", "l26"],
            ["qm", "set", vmid, "--net0", "virtio,bridge=vmbr0,tag=10"],
            ["qm", "set", vmid, "--serial0", "socket", "--vga", "serial0"],
            ["qm", "set", vmid, "--memory", "2048", "--cores", "2", "--cpu", "host"],
            ["qm", "set", vmid, "--scsi0", f"{template_storage}:0,import-from={temporary_directory}/{image_name},discard=on"],
            ["qm", "set", vmid, "--boot", "order=scsi0", "--scsihw", "virtio-scsi-single"],
            ["qm", "set", vmid, "--tablet", "0"],
            ["qm", "set", vmid, "--agent", "enabled=1,fstrim_cloned_disks=1"],
            ["qm", "set", vmid, "--ide2", f"{template_storage}:cloudinit"],
            ["qm", "set", vmid, "--ipconfig0", "ip6=auto,ip=dhcp"],
            ["qm", "set", vmid, "--sshkeys", ssh_keyfile],
            ["qm", "set", vmid, "--ciuser", username],
            ["qm", "template", vmid]
        ]

        for cmd in commands:
            run_command(cmd, verbose)
        logging.info(f"Successfully created template {name} [{vmid}]")
        return True
    
    except Exception as e:
        spinner.stop()
        logging.error(f"Failed to configure or create template {name} [{vmid}]")
        return False
    
    finally:
        spinner.stop()
    
def download_file(url, verbose):
    config = load_config()
    temporary_directory = config.get('default', 'temporary_directory')
    filename = os.path.basename(url)
    if verbose:
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        with open(os.path.join(temporary_directory, filename), 'wb') as file, tqdm(total=total_size, unit='iB', unit_scale=True) as bar:
            for data in response.iter_content(block_size):
                bar.update(len(data))
                file.write(data)
    else:
            response = requests.get(url, stream=True)
            with open(os.path.join(temporary_directory, filename), 'wb') as file:
                for data in response.iter_content(1024):
                    file.write(data)
            print("\033[32m✅ Finished downloading: {}\033[0m".format(filename))