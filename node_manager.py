#!/usr/bin/env python3
import os
import json
import subprocess
import paramiko
from rich.console import Console
from storage_manager import StorageManager

console = Console()

class NodeManager:
    def __init__(self, nodes_file="config/nodes.json"):
        self.nodes_file = nodes_file
        self.storage_manager = StorageManager()
        self._ensure_config_dir()
        self._load_nodes()
    
    def _ensure_config_dir(self):
        """Ensure config directory exists"""
        os.makedirs(os.path.dirname(self.nodes_file), exist_ok=True)
    
    def _load_nodes(self):
        """Load registered nodes from JSON file"""
        if os.path.exists(self.nodes_file):
            with open(self.nodes_file) as f:
                self.nodes = json.load(f)
        else:
            self.nodes = []
            self._save_nodes()
    
    def _save_nodes(self):
        """Save nodes to JSON file"""
        with open(self.nodes_file, 'w') as f:
            json.dump(self.nodes, f, indent=2)
    
    def register_node(self, name, host, username, key_file, port=22, cores=None):
        """Register a new worker node"""
        try:
            # Check if node already exists
            if any(node['name'] == name for node in self.nodes):
                console.print(f"[yellow]Node {name} already exists[/yellow]")
                return False
            
            # Test SSH connection
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(host, port, username, key_filename=key_file)
            except Exception as e:
                console.print(f"[red]SSH connection failed: {str(e)}[/red]")
                return False
            
            # Get CPU cores if not specified
            if not cores:
                stdin, stdout, stderr = ssh.exec_command('nproc')
                cores = int(stdout.read().decode().strip())
            
            # Install NFS client
            stdin, stdout, stderr = ssh.exec_command('sudo apt-get update && sudo apt-get install -y nfs-common')
            if stderr.read():
                console.print("[yellow]Warning: Error while installing NFS client[/yellow]")
            
            # Set up NFS mount
            server_ip = subprocess.check_output(['hostname', '-I']).decode().strip().split()[0]
            os.environ['K4ENUM_SERVER_IP'] = server_ip
            
            # Create mount script
            mount_script = f"""
            sudo mkdir -p {self.storage_manager.config['client']['mount_point']}
            echo "{server_ip}:{self.storage_manager.config['server']['path']} {self.storage_manager.config['client']['mount_point']} nfs {self.storage_manager.config['client']['options']} 0 0" | sudo tee -a /etc/fstab
            sudo mount -a
            """
            
            # Execute mount script
            stdin, stdout, stderr = ssh.exec_command(mount_script)
            if stderr.read():
                console.print("[yellow]Warning: Error while setting up NFS mount[/yellow]")
            
            # Create systemd service for Luigi worker
            service_script = f"""
            [Unit]
            Description=k4ENUM Luigi Worker
            After=network.target

            [Service]
            Type=simple
            User={username}
            Environment="PYTHONPATH=/k4enum"
            ExecStart=/usr/local/bin/luigid --background --pidfile /var/run/luigi.pid
            Restart=always

            [Install]
            WantedBy=multi-user.target
            """
            
            service_file = '/tmp/k4enum-worker.service'
            with open(service_file, 'w') as f:
                f.write(service_script)
            
            sftp = ssh.open_sftp()
            sftp.put(service_file, '/tmp/k4enum-worker.service')
            os.unlink(service_file)
            
            stdin, stdout, stderr = ssh.exec_command('sudo mv /tmp/k4enum-worker.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable k4enum-worker && sudo systemctl start k4enum-worker')
            if stderr.read():
                console.print("[yellow]Warning: Error while setting up systemd service[/yellow]")
            
            # Add node to registry
            node_info = {
                'name': name,
                'host': host,
                'port': port,
                'username': username,
                'key_file': key_file,
                'cores': cores
            }
            self.nodes.append(node_info)
            self._save_nodes()
            
            console.print(f"[green]Successfully registered node {name}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error registering node: {str(e)}[/red]")
            return False
        finally:
            if 'ssh' in locals():
                ssh.close()
    
    def remove_node(self, name):
        """Remove a registered node"""
        node = next((n for n in self.nodes if n['name'] == name), None)
        if not node:
            console.print(f"[yellow]Node {name} not found[/yellow]")
            return
        
        try:
            # Connect to node
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(node['host'], node['port'], node['username'], key_filename=node['key_file'])
            
            # Stop and remove systemd service
            stdin, stdout, stderr = ssh.exec_command('sudo systemctl stop k4enum-worker && sudo systemctl disable k4enum-worker && sudo rm /etc/systemd/system/k4enum-worker.service')
            
            # Unmount NFS
            stdin, stdout, stderr = ssh.exec_command(f'sudo umount {self.storage_manager.config["client"]["mount_point"]}')
            
            # Remove mount from fstab
            stdin, stdout, stderr = ssh.exec_command(f'sudo sed -i "\|{self.storage_manager.config["client"]["mount_point"]}|d" /etc/fstab')
            
            # Remove node from registry
            self.nodes = [n for n in self.nodes if n['name'] != name]
            self._save_nodes()
            
            console.print(f"[green]Successfully removed node {name}[/green]")
            
        except Exception as e:
            console.print(f"[red]Error removing node: {str(e)}[/red]")
        finally:
            if 'ssh' in locals():
                ssh.close()
    
    def list_nodes(self):
        """List all registered nodes"""
        return self.nodes
    
    def get_total_cores(self):
        """Get total number of CPU cores across all nodes"""
        return sum(node['cores'] for node in self.nodes)
    
    def test_connection(self, name):
        """Test connection to a node"""
        node = next((n for n in self.nodes if n['name'] == name), None)
        if not node:
            return False
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(node['host'], node['port'], node['username'], key_filename=node['key_file'], timeout=5)
            ssh.close()
            return True
        except:
            return False 