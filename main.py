import sys
import os
import socket
from functions import (
    load_config, runas_root, check_os, check_virt, check_tqdm, install_dependencies, check_and_delete_vm,
    customize_image, create_template, download_file, remove_file
)



def main():

    config = load_config()
    temporary_directory = config.get('default', 'temporary_directory', fallback='/tmp/')
    ssh_pubkeys_url = config.get('default', 'ssh_pubkeys_url')
    ssh_pubkeys_file = temporary_directory + ssh_pubkeys_url
    disk_images = config.get('diskimages')
    hostname = socket.gethostname()

    # This is a bit ugly but is the current way to deal with hosts having different storage configurations for vm disks
    # TODO: Read storage dynamically from Proxmox API
    if hostname not in config:
        print(f"Configuration for hostname '{hostname}' not found.\nYou need to add it to the config file.\n\nExample:\n\n[FQDN]\ntemplate_storage = local-lvm\ntemplate_vmids = 1000,1001,1002\n")
        sys.exit(1)

    if not check_os():
        print("\nThis script \033[4mcan only\033[0m be run on Proxmox VE.\n")
        sys.exit(1)

    if not runas_root():
        print("\nThis script \033[4mneeds\033[0m to be run as \033[1mroot\033[0m.\n")
        sys.exit(1)

    if not check_virt() or not check_tqdm():
        print("\nThis script \033[4mrequires\033[0m \033[1mpython3-tqdm\033[0m and \033[1mvirt-customize\033[0m to worky.\n\n\033[1mInstall them with:\033[0m\napt install python3-tqdm libguestfs-tools\n")
        sys.exit(1)

    if not config:
        print(f"Configuration for hostname '{hostname}' not found.")
        sys.exit(1)

    download_file(url=ssh_pubkeys_url)

    for name, value in disk_images.items():
        vmid, url = value.split('|')
        image_name = os.path.basename(url)

        if check_and_delete_vm(vmid, name, ):
            image_path = os.path.join(temporary_directory, image_name)
            if not os.path.isfile(image_path):
                download_file(url, temporary_directory, image_name)

            if "ubuntu" in name or "debian" in name:
                customize_image(temporary_directory, image_name, name)

            create_template(vmid, name, image_name, template_storage, temporary_directory, ssh_pubkeys_file, cloudinit_user)

    remove_file(temporary_directory)

if __name__ == "__main__":
    main()