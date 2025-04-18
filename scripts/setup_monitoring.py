#!/usr/bin/env python3
import os
import sys
import subprocess
from rich.console import Console

console = Console()

def check_root():
    """Check if script is running as root"""
    if os.geteuid() != 0:
        console.print("[red]This script must be run as root[/red]")
        sys.exit(1)

def create_service():
    """Create systemd service for monitoring"""
    service_content = """[Unit]
Description=k4ENUM Monitoring System
After=network.target

[Service]
Type=simple
User=root
Environment="PYTHONPATH=/k4enum"
ExecStart=/usr/bin/python3 /k4enum/monitoring.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
"""
    
    # Write service file
    service_file = '/etc/systemd/system/k4enum-monitor.service'
    with open(service_file, 'w') as f:
        f.write(service_content)
    
    # Reload systemd and enable service
    subprocess.run(['systemctl', 'daemon-reload'])
    subprocess.run(['systemctl', 'enable', 'k4enum-monitor'])
    subprocess.run(['systemctl', 'start', 'k4enum-monitor'])
    
    return True

def main():
    check_root()
    
    try:
        if create_service():
            console.print("[green]Monitoring service installed successfully![/green]")
            console.print("\nYou can:")
            console.print("1. Check service status:")
            console.print("   systemctl status k4enum-monitor")
            console.print("\n2. View logs:")
            console.print("   journalctl -u k4enum-monitor -f")
        else:
            console.print("[red]Failed to install monitoring service[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main() 