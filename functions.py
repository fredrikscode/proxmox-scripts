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

logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logHandler = RotatingFileHandler('debug.log', maxBytes=10000000, backupCount=3)
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
    logging.debug("Loaded config")
    return config

def runas_root():
    if os.geteuid() != 0:
        logging.error("Tried to run as non-root")
        return False
    else:
        logging.debug("Running as root")
        return True

def check_os():
    if 'pve' in platform.platform():
        logging.debug("Running on Proxmox VE")
        return True
    else:
        logging.error("Not running on Proxmox VE")
        return False

def run_command(cmd):
        logging.debug(f"Asked to run command: {cmd}")
        subprocess.run(cmd, check=True)
        logging.debug(f"Ran command: {cmd}")

def check_virt():
    try:
        logging.debug(f"Checking if virt-customize is installed")
        run_command(["virt-customize", "--version"])
        logging.debug("virt-customize is installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\033[31m❌ virt-customize is not installed or not found in PATH\033[0m")
        logging.error("virt-customize is not installed or not found in PATH")
        return False

def check_tqdm():
    try:
        logging.debug(f"Trying to import python3-tqdm")
        from tqdm import tqdm
        logging.debug("python3-tqdm is installed")
        return True
    
    except ImportError:
        logging.error("python3-tqdm is not installed")
        return False

def remove_file(path, filename):
    try:
        logging.debug(f"Trying to remove {filename} from {path}")
        os.remove(os.path.join(path, filename))
        logging.debug(f"Removed {filename} from {path}")

    except FileNotFoundError:
        print(f"\033[31m❌ {filename} not found in {path}\033[0m")
        logging.debug(f"Could not find file {filename} in path {path}")

def install_dependencies():
    try:
        run_command(["apt", "install", "-y", "python3-tqdm", "libguestfs-tools"])
        logging.info("Installed dependencies")
        return True
    except subprocess.CalledProcessError:
        logging.error("Failed to install dependencies")
        return False

def check_and_delete_vm(vmid, name):
    success_message = f"\033[32m✅ Removed template {name} [{vmid}]\033[0m"
    failure_message = f"\033[31m❌ Error while removing template {name} [{vmid}]\033[0m"
    spinner = Spinner(f"Checking if template {name} exists and deleting it if it does", success_message, failure_message)
    spinner.start()
    try:
        logging.debug(f"Trying to check if template VM ({name} - {vmid}) exists")
        run_command(["qm", "status", vmid])
    except subprocess.CalledProcessError:
        spinner.stop()
        return True

    try:
        logging.debug(f"Trying to delete template VM ({name} - {vmid})")
        run_command(["qm", "destroy", vmid])
        spinner.stop()
        logging.info(f"Deleted template VM ({name} - {vmid})")
        return True
    except subprocess.CalledProcessError:
        spinner.stop()
        logging.error(f"Failed to delete template VM ({name} - {vmid})")
        return False
    
def customize_image(temporary_directory, image_name, name):
    success_message = f"\033[32m✅ Customized image for {name}\033[0m"
    failure_message = f"\033[31m❌ Error while customizing image for {name}\033[0m"
    spinner = Spinner(f"Customizing image for {name}", success_message, failure_message)
    try:
        logging.debug(f"Trying to customize {temporary_directory}/{image_name}")
        spinner.start()
        run_command(["virt-customize", "-a", f"{temporary_directory}/{image_name}", "--firstboot-install", "qemu-guest-agent"])
        logging.debug(f"Added qemu-guest-agent installation on first boot in {image_name}")
        run_command(["virt-customize", "-a", f"{temporary_directory}/{image_name}", "--firstboot-command", "systemctl enable --now qemu-guest-agent"])
        logging.debug(f"Enabled qemu-guest-agent on first boot in {image_name}")
    except Exception as e:
        logging.error(f"Failed to customize {image_name}")
        print("ERROR:", e)
    finally:
        spinner.stop()

def create_template(vmid, name, image_name, template_storage, temporary_directory, ssh_pubkeys, cloudinit_user):
    success_message = f"\033[32m✅ Created template {name}\033[0m"
    failure_message = f"\033[31m❌ Error while creating template {name}\033[0m"
    spinner = Spinner(f"Trying to create template {name}", success_message, failure_message)

    config = load_config()
    cloudinit_user = config.get('default', 'cloudinit_user')

    try:
        spinner.start()
        logging.debug(f"Trying to create template {name} [{vmid}]\nImage name: {image_name}\nTemplate storage: {template_storage}\nTemporary directory: {temporary_directory}\nSSH pubkeys: {ssh_pubkeys}\nCloudinit user: {cloudinit_user}")
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
            ["qm", "set", vmid, "--sshkeys", ssh_pubkeys],
            ["qm", "set", vmid, "--ciuser", cloudinit_user],
            ["qm", "template", vmid]
        ]

        for cmd in commands:
            logging.debug(f"Running command: {cmd}")
            run_command(cmd)
        logging.debug(f"Successfully created template {name} [{vmid}]")
        return True
    
    except Exception as e:
        spinner.stop()
        logging.error(f"Failed to configure or create template {name} [{vmid}]: {e}")
        return False
    
    finally:
        spinner.stop()
    
def download_file(url):
    config = load_config()
    temporary_directory = config.get('default', 'temporary_directory')
    filename = os.path.basename(url)
    # response = requests.get(url, stream=True)
    # total_size = int(response.headers.get('content-length', 0))
    # block_size = 1024
    # with open(os.path.join(temporary_directory, filename), 'wb') as file, tqdm(total=total_size, unit='iB', unit_scale=True) as bar:
    #     for data in response.iter_content(block_size):
    #         bar.update(len(data))
    #         file.write(data)
    logging.debug(f"Trying to download {url} to {os.path.join(temporary_directory, filename)}")
    response = requests.get(url, stream=True)
    with open(os.path.join(temporary_directory, filename), 'wb') as file:
        for data in response.iter_content(1024):
            file.write(data)
    print("\033[32m✅ Finished downloading: {}\033[0m".format(filename))