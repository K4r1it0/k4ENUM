#!/usr/bin/env python3
import os
import sys
import subprocess
from rich.console import Console
from storage_manager import StorageManager

console = Console()

def check_root():
    """Check if script is running as root"""
    if os.geteuid() != 0:
        console.print("[red]This script must be run as root[/red]")
        sys.exit(1)

def install_nfs_server():
    """Install NFS server package"""
    try:
        console.print("Installing NFS server...")
        subprocess.run(['apt-get', 'update'], check=True)
        subprocess.run(['apt-get', 'install', '-y', 'nfs-kernel-server'], check=True)
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error installing NFS server: {str(e)}[/red]")
        return False

def main():
    check_root()
    
    if not install_nfs_server():
        sys.exit(1)
    
    # Initialize storage manager
    storage_manager = StorageManager()
    
    # Set up NFS server
    if storage_manager.setup_server():
        console.print("[green]Storage server setup completed successfully![/green]")
        console.print("\nNext steps:")
        console.print("1. Register worker nodes using:")
        console.print("   python3 scan.py --nodes register --name <node_name> --host <host> --username <user> --key-file <key_file>")
        console.print("\n2. Start the central Luigi scheduler:")
        console.print("   luigid")
        console.print("\n3. Run workflows with distributed execution:")
        console.print("   python3 scan.py -w <workflow> -c -d")
    else:
        console.print("[red]Storage server setup failed[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main() 