#!/usr/bin/env python3
import os
import yaml
import subprocess
from pathlib import Path
from rich.console import Console

console = Console()

class StorageManager:
    def __init__(self, config_path="config/storage.yaml"):
        self.config_path = config_path
        self.load_config()
        
    def load_config(self):
        """Load storage configuration from YAML file"""
        try:
            with open(self.config_path) as f:
                self.config = yaml.safe_load(f)['storage']
        except Exception as e:
            console.print(f"[red]Error loading storage config: {str(e)}[/red]")
            raise
    
    def setup_server(self):
        """Set up NFS server on the main node"""
        try:
            # Create base directory if it doesn't exist
            base_path = self.config['server']['path']
            os.makedirs(base_path, exist_ok=True)
            
            # Create subdirectories
            for dir_name in self.config['directories']:
                os.makedirs(os.path.join(base_path, dir_name), exist_ok=True)
            
            # Set up NFS exports
            exports_line = f"{base_path} *(rw,sync,no_subtree_check)"
            with open('/etc/exports', 'a') as f:
                f.write(f"\n{exports_line}")
            
            # Apply exports and start NFS server
            subprocess.run(['exportfs', '-ra'])
            subprocess.run(['systemctl', 'restart', 'nfs-kernel-server'])
            
            console.print("[green]NFS server setup completed successfully[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error setting up NFS server: {str(e)}[/red]")
            return False
    
    def setup_client(self, create_mount_point=True):
        """Set up NFS client on a worker node"""
        try:
            mount_point = self.config['client']['mount_point']
            
            if create_mount_point:
                os.makedirs(mount_point, exist_ok=True)
            
            # Add mount to fstab for persistence
            server_ip = os.environ.get('K4ENUM_SERVER_IP', 'localhost')
            server_path = self.config['server']['path']
            mount_options = self.config['client']['options']
            
            fstab_line = f"{server_ip}:{server_path} {mount_point} nfs {mount_options} 0 0"
            
            # Check if mount already exists in fstab
            with open('/etc/fstab', 'r') as f:
                if any(line.strip() == fstab_line for line in f):
                    console.print("[yellow]Mount point already exists in fstab[/yellow]")
                else:
                    with open('/etc/fstab', 'a') as f:
                        f.write(f"\n{fstab_line}")
            
            # Mount immediately
            subprocess.run(['mount', '-a'])
            
            console.print("[green]NFS client setup completed successfully[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error setting up NFS client: {str(e)}[/red]")
            return False
    
    def get_path(self, directory, filename=None):
        """Get full path for a file in shared storage"""
        if directory not in self.config['directories']:
            raise ValueError(f"Invalid directory: {directory}")
        
        path = os.path.join(self.config['server']['path'], directory)
        if filename:
            path = os.path.join(path, filename)
        return path
    
    def ensure_directory(self, directory):
        """Ensure a directory exists in shared storage"""
        if directory not in self.config['directories']:
            raise ValueError(f"Invalid directory: {directory}")
        
        path = os.path.join(self.config['server']['path'], directory)
        os.makedirs(path, exist_ok=True)
        return path
    
    def cleanup_temp(self):
        """Clean up temporary files in shared storage"""
        temp_dir = os.path.join(self.config['server']['path'], 'temp')
        if os.path.exists(temp_dir):
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        os.rmdir(item_path)
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not remove {item_path}: {str(e)}[/yellow]") 