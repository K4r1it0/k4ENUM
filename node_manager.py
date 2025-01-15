import os
import yaml
import paramiko
from rich.console import Console
from pathlib import Path
import traceback

console = Console()

class NodeManager:
    def __init__(self):
        self.nodes_file = "nodes.yaml"
        try:
            self.nodes = self._load_nodes()
            console.print(f"[dim]Loaded {len(self.nodes)} nodes from configuration[/dim]")
        except Exception as e:
            console.print(f"[red]Error loading nodes: {str(e)}[/red]")
            self.nodes = []
    
    def _load_nodes(self):
        """Load nodes configuration from YAML file"""
        try:
            if os.path.exists(self.nodes_file):
                with open(self.nodes_file) as f:
                    config = yaml.safe_load(f)
                    console.print(f"[dim]Loaded config: {config}[/dim]")
                    if config is None:
                        config = {'nodes': {'remote_nodes': []}}
                    if not isinstance(config, dict):
                        raise ValueError(f"Invalid YAML structure: {config}")
                    nodes = config.get('nodes', {}).get('remote_nodes', [])
                    if not isinstance(nodes, list):
                        raise ValueError(f"Invalid nodes structure: {nodes}")
                    return nodes
            
            # Create initial nodes file structure
            config = {'nodes': {'remote_nodes': []}}
            with open(self.nodes_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            console.print(f"[dim]Created new nodes configuration file[/dim]")
            return []
        except Exception as e:
            console.print(f"[red]Error in _load_nodes: {str(e)}\n{traceback.format_exc()}[/red]")
            raise
    
    def _save_nodes(self):
        """Save nodes configuration to YAML file"""
        try:
            config = {'nodes': {'remote_nodes': self.nodes}}
            with open(self.nodes_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            console.print(f"[dim]Saved {len(self.nodes)} nodes to configuration[/dim]")
        except Exception as e:
            console.print(f"[red]Error saving nodes: {str(e)}[/red]")
            raise
    
    def _load_ssh_key(self, key_file):
        """Load SSH key of any supported type"""
        key_file = os.path.expanduser(key_file)
        console.print(f"[dim]Loading SSH key from {key_file}[/dim]")
        
        if not os.path.exists(key_file):
            raise Exception(f"SSH key file not found: {key_file}")
        
        # Read key file content
        with open(key_file, 'r') as f:
            key_content = f.read()
            console.print(f"[dim]Key file content length: {len(key_content)} chars[/dim]")
        
        errors = []
        
        # Try loading as ED25519 key first (since that's what we're using)
        try:
            console.print("[dim]Trying ED25519 format...[/dim]")
            key = paramiko.Ed25519Key.from_private_key_file(key_file)
            console.print("[dim]Successfully loaded as ED25519[/dim]")
            return key
        except Exception as e:
            errors.append(f"ED25519: {str(e)}")
        
        # Try loading as RSA key
        try:
            console.print("[dim]Trying RSA format...[/dim]")
            key = paramiko.RSAKey.from_private_key_file(key_file)
            console.print("[dim]Successfully loaded as RSA[/dim]")
            return key
        except Exception as e:
            errors.append(f"RSA: {str(e)}")
        
        # Try loading as ECDSA key
        try:
            console.print("[dim]Trying ECDSA format...[/dim]")
            key = paramiko.ECDSAKey.from_private_key_file(key_file)
            console.print("[dim]Successfully loaded as ECDSA[/dim]")
            return key
        except Exception as e:
            errors.append(f"ECDSA: {str(e)}")
        
        # Try loading as DSS key
        try:
            console.print("[dim]Trying DSS format...[/dim]")
            key = paramiko.DSSKey.from_private_key_file(key_file)
            console.print("[dim]Successfully loaded as DSS[/dim]")
            return key
        except Exception as e:
            errors.append(f"DSS: {str(e)}")
        
        raise Exception(f"Failed to load SSH key. Errors:\n" + "\n".join(errors))
    
    def register_node(self, name, host, username, key_file, port=22, cores=None):
        """Register a new remote node"""
        console.print(f"[dim]Registering node {name} ({username}@{host}:{port})[/dim]")
        
        # Validate SSH connection
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Load SSH key
            key = self._load_ssh_key(key_file)
            console.print(f"[dim]Successfully loaded SSH key[/dim]")
            
            # Connect to remote host
            console.print(f"[dim]Connecting to {host}...[/dim]")
            ssh.connect(hostname=host, port=port, username=username, pkey=key)
            console.print(f"[dim]Successfully connected[/dim]")
            
            # Get core count if not specified
            if cores is None:
                console.print(f"[dim]Detecting CPU cores...[/dim]")
                _, stdout, stderr = ssh.exec_command('nproc')
                exit_status = stdout.channel.recv_exit_status()
                if exit_status != 0:
                    error = stderr.read().decode().strip()
                    raise Exception(f"Failed to get core count: {error}")
                cores = int(stdout.read().decode().strip())
                console.print(f"[dim]Detected {cores} cores[/dim]")
            
            # Add node to configuration
            node = {
                'name': name,
                'host': host,
                'port': port,
                'username': username,
                'key_file': key_file,
                'cores': cores
            }
            
            # Remove existing node with same name if exists
            self.nodes = [n for n in self.nodes if n['name'] != name]
            self.nodes.append(node)
            self._save_nodes()
            
            # Setup node
            console.print(f"[dim]Setting up node environment...[/dim]")
            self._setup_node(ssh, node)
            
            console.print(f"[green]Successfully registered node {name}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error registering node {name}:\n{traceback.format_exc()}[/red]")
            return False
        finally:
            if 'ssh' in locals():
                ssh.close()
    
    def _setup_node(self, ssh, node):
        """Setup remote node with required dependencies"""
        commands = [
            # Check Python version
            'python3 --version',
            # Install required system packages
            'apt update && apt install -y python3-venv python3-pip',
            # Create virtual environment (with system packages to avoid pip issues)
            'python3 -m venv ~/k4enum_venv --system-site-packages',
            # Update pip
            '. ~/k4enum_venv/bin/activate && pip install --upgrade pip',
            # Install dependencies
            '. ~/k4enum_venv/bin/activate && pip install "luigi>=3.4.0" "paramiko>=3.4.0" "pyyaml>=6.0.1" "rich>=13.7.0"',
            # Create work directory
            'mkdir -p ~/k4enum_work'
        ]
        
        for cmd in commands:
            console.print(f"[dim]Running: {cmd}[/dim]")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            # Get command output
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            
            if exit_status != 0:
                console.print(f"[red]Command failed with status {exit_status}[/red]")
                console.print(f"[red]stdout: {out}[/red]")
                console.print(f"[red]stderr: {err}[/red]")
                raise Exception(f"Command failed: {err if err else out}")
            
            if out:
                console.print(f"[dim]Output: {out}[/dim]")
            console.print(f"[dim]Command completed successfully[/dim]")
    
    def remove_node(self, name):
        """Remove a registered node"""
        self.nodes = [n for n in self.nodes if n['name'] != name]
        self._save_nodes()
        console.print(f"[green]Removed node {name}[/green]")
    
    def list_nodes(self):
        """List all registered nodes"""
        return self.nodes
    
    def get_node(self, name):
        """Get node configuration by name"""
        for node in self.nodes:
            if node['name'] == name:
                return node
        return None
    
    def get_total_cores(self):
        """Get total number of cores across all nodes"""
        return sum(node['cores'] for node in self.nodes)
    
    def test_connection(self, name):
        """Test connection to a node"""
        node = self.get_node(name)
        if not node:
            console.print(f"[red]Node {name} not found[/red]")
            return False
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Load SSH key
            key = self._load_ssh_key(node['key_file'])
            
            # Test connection
            ssh.connect(node['host'], port=node['port'], username=node['username'], pkey=key)
            console.print(f"[green]Successfully connected to node {name}[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Error connecting to node {name}: {str(e)}[/red]")
            return False
        finally:
            if 'ssh' in locals():
                ssh.close() 