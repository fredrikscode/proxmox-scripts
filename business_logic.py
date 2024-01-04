import os
import platform
import subprocess
import requests

def check_os(verbose):
    if 'pve' in platform.platform():
        return True
    else:
        return False

def run_command(cmd, verbose):
    if verbose:
        subprocess.run(cmd, check=True)
    else:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def check_virt(verbose):
    try:
        run_command(["virt-customize", "--version"], verbose)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        if verbose:
            print("\033[31m❌ virt-customize is not installed or not found in PATH\033[0m")
        return False

def check_tqdm(verbose):
    try:
        from tqdm import tqdm
        return True
    
    except ImportError:
        return False
    
    if verbose:
        if 'tqdm' in sys.modules:
            print("\033[32m✅ python3-tqdm is installed\033[0m")
        else:
            print("\033[31m❌ python3-tqdm is not installed\033[0m")
def install_dependencies(verbose):
    try:
        run_command(["apt", "install", "-y", "python3-tqdm", "libguestfs-tools"], verbose)
        return True
    except subprocess.CalledProcessError:
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
        run_command(["virt-customize", "-a", f"{temp_dir}/{image_name}", "--firstboot-command", "systemctl enable --now qemu-guest-agent"], verbose)
    except Exception as e:
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
        return True
    
    except Exception as e:
        print("ERROR:", e)
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