import argparse
import sys
from business_logic import (
    runas_root, check_os, check_virt, check_tqdm, install_dependencies, check_and_delete_vm,
    customize_image, create_template, download_file
)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Proxmox VM Template Creation Script")
    parser.add_argument("-v", "--verbose", help="Increase output verbosity", action="store_true")
    parser.add_argument("-li", "--log-info", help="Enable logging INFO", action="store_true")
    parser.add_argument("-ld", "--log-debug", help="Enable logging DEBUG", action="store_true")

    return parser.parse_args()

def main():
    args = parse_arguments()

    # Check prerequisites
    if not check_os(args.verbose):
        print("\nThis script \033[4mcan only\033[0m be run on Proxmox VE.\n")
        sys.exit(1)

    if not check_virt(args.verbose) or not check_tqdm(args.verbose):
        print("\nThis script \033[4mrequires\033[0m \033[1mpython3-tqdm\033[0m and \033[1mvirt-customize\033[0m to worky.\n\n\033[1mInstall them with:\033[0m\napt install python3-tqdm libguestfs-tools\n")
        sys.exit(1)

    if not runas_root():
        print("\nThis script \033[4mneeds\033[0m to be run as \033[1mroot\033[0m.\n")
        sys.exit(1)

if __name__ == "__main__":
    main()