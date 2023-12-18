import os
import socket
import subprocess
import requests
from tqdm import tqdm

def vm_exists(vmid):
    print(f"Checking if VMID {vmid} exists..")
    try:
        subprocess.check_output(["qm", "status", vmid], stderr=subprocess.DEVNULL)
        print("VMID already exists. Proceeding to delete..")
        try:
            subprocess.check_call(["qm", "destroy", vmid])
            return True
        except subprocess.CalledProcessError:
            return False
    except subprocess.CalledProcessError:
        return True

def create_template(vmid, name, image_name, template_storage, temp_dir, ssh_keyfile, username):
    print(f"Creating template {name} ({vmid})")
    commands = [
        ["qm", "create", vmid, "--name", name, "--ostype", "l26"],
        ["qm", "set", vmid, "--net0", "virtio,bridge=vmbr0"],
        ["qm", "set", vmid, "--serial0", "socket", "--vga", "serial0"],
        ["qm", "set", vmid, "--memory", "2048", "--cores", "2", "--cpu", "host"],
        ["qm", "set", vmid, "--scsi0", f"{template_storage}:0,import-from={temp_dir}/{image_name},discard=on"],
        ["qm", "set", vmid, "--boot", "order=scsi0", "--scsihw", "virtio-scsi-single"],
        ["qm", "set", vmid, "--agent", "enabled=1,fstrim_cloned_disks=1"],
        ["qm", "set", vmid, "--ide2", f"{template_storage}:cloudinit"],
        ["qm", "set", vmid, "--ipconfig0", "ip6=auto,ip=dhcp"],
        ["qm", "set", vmid, "--sshkeys", ssh_keyfile],
        ["qm", "set", vmid, "--ciuser", username],
        ["qm", "template", vmid]
    ]

    for cmd in commands:
        subprocess.check_call(cmd)

def download_file(url, temp_dir, filename):
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024
    temp_file_path = os.path.join(temp_dir, filename)
    with open(temp_file_path, 'wb') as file, tqdm(total=total_size, unit='iB', unit_scale=True) as bar:
        for data in response.iter_content(block_size):
            bar.update(len(data))
            file.write(data)

def main():
    temp_dir = "/tmp"
    ssh_keyfile = "/tmp/keys_internal_servers"
    username = "admin"
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
        "ubuntu20.04": f"{template_vmids[1]}|https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-arm64.img",
        "debian12": f"{template_vmids[2]}|https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2"
    }

    download_file("https://raw.githubusercontent.com/fredrikscode/ssh-keys/main/internal_servers", temp_dir, ssh_keyfile)

    for name, value in disk_images.items():
        vmid, url = value.split('|')
        image_name = os.path.basename(url)

        if vm_exists(vmid):
            image_path = os.path.join(temp_dir, image_name)
            if not os.path.isfile(image_path):
                print(f"Downloading disk image for {name} to {temp_dir}..")
                download_file(url, temp_dir, image_name)
            else:
                print("Disk image exists")

            create_template(vmid, name, image_name, template_storage, temp_dir, ssh_keyfile, username)

    os.remove(ssh_keyfile)

if __name__ == "__main__":
    main()