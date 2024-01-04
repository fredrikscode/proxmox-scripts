import os
import socket
import subprocess
import requests
import sys
from tqdm import tqdm
import argparse
import logging

parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="Increase output verbosity", action="store_true")
args = parser.parse_args()

def check_prerequisites():
    print("Checking prerequisites..")
    prerequisites = {
        "virt-customize": check_virt,
        "python3-tqdm": check_tqdm
    }

    all_passed = True

    for item, check_function in prerequisites.items():
        if check_function():
            print("\033[32m✅ {}\033[0m".format(item))
        else:
            print("\033[31m❌ {}\033[0m".format(item))
            all_passed = False

    if not all_passed:
        sys.exit(1)

def run_command(cmd, verbose):
    if verbose:
        subprocess.run(cmd, check=True)
    else:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def check_virt():
    try:
        run_command(["virt-customize", "--version"], args.verbose)
        return True
    
    except subprocess.CalledProcessError:
        return False

def check_tqdm():
    try:
        run_command(["dpkg", "-s", "python3-tqdm"], args.verbose)
        return True
    
    except subprocess.CalledProcessError:
        return False

def check_and_delete_vm(vmid):
    try:
        run_command(["qm", "status", vmid], args.verbose)
    except subprocess.CalledProcessError:
        return True

    try:
        run_command(["qm", "destroy", vmid], args.verbose)
        return True
    except subprocess.CalledProcessError:
        return False

def customize_image(temp_dir, image_name):
    try:
        run_command(["virt-customize", "-a", f"{temp_dir}/{image_name}", "--firstboot-install", "qemu-guest-agent"], args.verbose)
        run_command(["virt-customize", "-a", f"{temp_dir}/{image_name}", "--firstboot-command", "systemctl enable --now qemu-guest-agent"], args.verbose)
    except Exception as e:
        print("ERROR:", e)

def create_template(vmid, name, image_name, template_storage, temp_dir, ssh_keyfile, username):
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
            run_command(cmd, args.verbose)
        return True
    
    except Exception as e:
        print("ERROR:", e)
        return False 

def download_file(url, temp_dir, filename):
    if args.verbose:
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

def main():
    check_prerequisites()
    temp_dir = "/tmp"
    ssh_keyfile = "/tmp/keys_internal_servers"
    username = "fredrik"
    hostname = socket.gethostname()

    config_mapping = {
        "titan.freddan.io": {"template_storage": "vm-storage", "template_vmids": ["3000", "3001", "3002"]},
        "hive.freddan.io": {"template_storage": "local-lvm", "template_vmids": ["2000", "2001", "2002"]},
        "nano.freddan.io": {"template_storage": "local-lvm", "template_vmids": ["1000", "1001", "1002"]}
    }

    config = config_mapping.get(hostname)
    template_storage = config["template_storage"]
    template_vmids = config["template_vmids"]

    disk_images = {
        "alma9.3": f"{template_vmids[0]}|https://repo.almalinux.org/almalinux/9.3/cloud/x86_64/images/AlmaLinux-9-GenericCloud-latest.x86_64.qcow2",
        "ubuntu20.04": f"{template_vmids[1]}|https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img",
        "debian12": f"{template_vmids[2]}|https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2"
    }

    download_file("https://raw.githubusercontent.com/fredrikscode/ssh-keys/main/internal_servers", temp_dir, ssh_keyfile)

    for name, value in disk_images.items():
        vmid, url = value.split('|')
        image_name = os.path.basename(url)

        if check_and_delete_vm(vmid):
            image_path = os.path.join(temp_dir, image_name)
            if not os.path.isfile(image_path):
                download_file(url, temp_dir, image_name)

            if "ubuntu" in name or "debian" in name:
                customize_image(temp_dir, image_name)

            if create_template(vmid, name, image_name, template_storage, temp_dir, ssh_keyfile, username):
                print("\033[32m✅ Template created: {}\033[0m".format(name))
            else:
                print("\033[31m❌ Template Creation Failed: {}\033[0m".format(name))

    os.remove(ssh_keyfile)

if __name__ == "__main__":
    main()
