import argparse
import sys
import os
import socket
from functions import (
    load_config, runas_root, check_os, check_virt, check_tqdm, install_dependencies, check_and_delete_vm,
    customize_image, create_template, download_file
)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Proxmox VM Template Creation Script")
    parser.add_argument("-v", "--verbose", help="Increase output verbosity", action="store_true")

    return parser.parse_args()

def main():
    args = parse_arguments()

    config = load_config()
    temporary_directory = config.get('default', 'temporary_directory', fallback='/tmp/')
    ssh_pubkeys_file = config.get('default', 'ssh_pubkeys_file')
    username = "fredrik"
    hostname = socket.gethostname()

    print(f"DEBUG: {hostname}")
    # This is a bit ugly but is the current way to deal with hosts having different storage configurations for vm disks
    if hostname not in config:
        print(f"Configuration for hostname '{hostname}' not found.\nYou need to add it to the config file.\n\nExample:\n\n[FQDN]\ntemplate_storage = local-lvm\ntemplate_vmids = 1000,1001,1002\n")
        sys.exit(1)

    if not check_os(args.verbose):
        print("\nThis script \033[4mcan only\033[0m be run on Proxmox VE.\n")
        sys.exit(1)

    if not runas_root():
        print("\nThis script \033[4mneeds\033[0m to be run as \033[1mroot\033[0m.\n")
        sys.exit(1)

    if not check_virt(args.verbose) or not check_tqdm(args.verbose):
        print("\nThis script \033[4mrequires\033[0m \033[1mpython3-tqdm\033[0m and \033[1mvirt-customize\033[0m to worky.\n\n\033[1mInstall them with:\033[0m\napt install python3-tqdm libguestfs-tools\n")
        sys.exit(1)

    config_mapping = {
        "titan.freddan.io": {"template_storage": "vm-storage", "template_vmids": ["3000", "3001", "3002"]},
        "hive.freddan.io": {"template_storage": "local-lvm", "template_vmids": ["2000", "2001", "2002"]},
        "nano.freddan.io": {"template_storage": "local-lvm", "template_vmids": ["1000", "1001", "1002"]}
    }

    config = config_mapping.get(hostname)
    if not config:
        print(f"Configuration for hostname '{hostname}' not found.")
        sys.exit(1)
    template_storage = config["template_storage"]
    template_vmids = config["template_vmids"]

    disk_images = {
        "alma9.3": f"{template_vmids[0]}|https://repo.almalinux.org/almalinux/9.3/cloud/x86_64/images/AlmaLinux-9-GenericCloud-latest.x86_64.qcow2",
        "ubuntu20.04": f"{template_vmids[1]}|https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img",
        "debian12": f"{template_vmids[2]}|https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2"
    }

    download_file(url=ssh_pubkeys_file, verbose=args.verbose)

    for name, value in disk_images.items():
        vmid, url = value.split('|')
        image_name = os.path.basename(url)

        if check_and_delete_vm(vmid, name, args.verbose):
            image_path = os.path.join(temporary_directory, image_name)
            if not os.path.isfile(image_path):
                download_file(url, temporary_directory, image_name, args.verbose)

            if "ubuntu" in name or "debian" in name:
                customize_image(temporary_directory, image_name, name, args.verbose)

            create_template(vmid, name, image_name, template_storage, temporary_directory, ssh_pubkeys_file, username, args.verbose)

    os.remove(ssh_pubkeys_file)

if __name__ == "__main__":
    main()