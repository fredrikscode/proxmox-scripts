import os
import sys
import platform
import subprocess
import requests
import logging
from logging.handlers import RotatingFileHandler

logging.basicConfig(filename='pve-templates.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logHandler = RotatingFileHandler('pve-templates.log', maxBytes=10000000, backupCount=3)
logHandler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

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

def check_and_delete_vm(vmid, verbose):
    try:
        run_command(["qm", "status", vmid], verbose)
    except subprocess.CalledProcessError:
        return True

    try:
        run_command(["qm", "destroy", vmid], verbose)
        return True
    except subprocess.CalledProcessError:
        return False
    
def customize_image(temp_dir, image_name, verbose):
    try:
        run_command(["virt-customize", "-a", f"{temp_dir}/{image_name}", "--firstboot-install", "qemu-guest-agent"], verbose)
        logging.info("Added qemu-guest-agent installation on first boot to image")
        run_command(["virt-customize", "-a", f"{temp_dir}/{image_name}", "--firstboot-command", "systemctl enable --now qemu-guest-agent"], verbose)
        logging.info("Enabled qemu-guest-agent on first boot")
    except Exception as e:
        logging.error("Failed to customize image")
        print("ERROR:", e)

def create_template(vmid, name, image_name, template_storage, temp_dir, ssh_keyfile, username, verbose):
    try:
        commands = [
            ["qm", "create", vmid, "--name", name, "--ostype", "l26"],
            ["qm", "set", vmid, "--net0", "virtio,bridge=vmbr0,tag=10"],
            ["qm", "set", vmid, "--serial0", "socket", "--vga", "serial0"],
            ["qm", "set", vmid, "--memory", "2048", "--cores", "2", "--cpu", "host"],
            ["qm", "set", vmid, "--scsi0", f"{template_storage}:0,import-from={temp_dir}/{image_name},discard=on"],
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
        logging.info("Successfully configured the VM")
        return True
    
    except Exception as e:
        logging.error("Failed to configure the VM")
        return False
    
def download_file(url, temp_dir, filename, verbose):
    if verbose:
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        temp_file_path = os.path.join(temp_dir, filename)
        with open(temp_file_path, 'wb') as file, tqdm(total=total_size, unit='iB', unit_scale=True) as bar:
            for data in response.iter_content(block_size):
                bar.update(len(data))
                file.write(data)
    else:
            response = requests.get(url, stream=True)
            temp_file_path = os.path.join(temp_dir, filename)
            with open(temp_file_path, 'wb') as file:
                for data in response.iter_content(1024):
                    file.write(data)
            print("\033[32m✅ Finished downloading: {}\033[0m".format(filename))