#!/usr/bin/env python3
import os
import time
import json
import psutil
import logging
import paramiko
from datetime import datetime
from rich.console import Console
from rich.table import Table
from storage_manager import StorageManager
from node_manager import NodeManager

console = Console()

class MonitoringSystem:
    def __init__(self):
        self.storage_manager = StorageManager()
        self.node_manager = NodeManager()
        self.setup_logging()
    
    def setup_logging(self):
        """Set up logging configuration"""
        log_dir = self.storage_manager.get_path('logs', '')
        os.makedirs(log_dir, exist_ok=True)
        
        # Main log file
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(log_dir, 'k4enum.log')),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('k4enum.monitor')
    
    def get_node_metrics(self, node):
        """Get health metrics from a node"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                node['host'],
                node['port'],
                node['username'],
                key_filename=node['key_file'],
                timeout=5
            )
            
            # Get CPU usage
            stdin, stdout, stderr = ssh.exec_command('top -bn1 | grep "Cpu(s)" | sed "s/.*, *\\([0-9.]*\\)%* id.*/\\1/" | awk \'{print 100 - $1}\'')
            cpu_usage = float(stdout.read().decode().strip())
            
            # Get memory usage
            stdin, stdout, stderr = ssh.exec_command('free | grep Mem | awk \'{print $3/$2 * 100.0}\'')
            memory_usage = float(stdout.read().decode().strip())
            
            # Get disk usage
            stdin, stdout, stderr = ssh.exec_command(f'df {self.storage_manager.config["client"]["mount_point"]} | tail -1 | awk \'{{print $5}}\' | sed \'s/%//\'')
            disk_usage = float(stdout.read().decode().strip())
            
            # Get active Luigi workers
            stdin, stdout, stderr = ssh.exec_command('ps aux | grep "luigid" | grep -v grep | wc -l')
            luigi_workers = int(stdout.read().decode().strip())
            
            # Get system load
            stdin, stdout, stderr = ssh.exec_command('uptime | awk -F\'load average:\' \'{ print $2 }\' | awk -F\', \' \'{ print $1 }\'')
            load_avg = float(stdout.read().decode().strip())
            
            ssh.close()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'node': node['name'],
                'status': 'online',
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'disk_usage': disk_usage,
                'luigi_workers': luigi_workers,
                'load_avg': load_avg
            }
            
        except Exception as e:
            self.logger.error(f"Error getting metrics from node {node['name']}: {str(e)}")
            return {
                'timestamp': datetime.now().isoformat(),
                'node': node['name'],
                'status': 'offline',
                'error': str(e)
            }
    
    def collect_logs(self, node):
        """Collect logs from a node"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                node['host'],
                node['port'],
                node['username'],
                key_filename=node['key_file'],
                timeout=5
            )
            
            # Get Luigi worker logs
            stdin, stdout, stderr = ssh.exec_command('cat /var/log/k4enum-worker.log')
            worker_logs = stdout.read().decode()
            
            # Get system logs related to k4enum
            stdin, stdout, stderr = ssh.exec_command('journalctl -u k4enum-worker --since "1 hour ago"')
            system_logs = stdout.read().decode()
            
            ssh.close()
            
            # Save logs to shared storage
            log_dir = self.storage_manager.get_path('logs', node['name'])
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            with open(os.path.join(log_dir, f'worker_{timestamp}.log'), 'w') as f:
                f.write(worker_logs)
            
            with open(os.path.join(log_dir, f'system_{timestamp}.log'), 'w') as f:
                f.write(system_logs)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error collecting logs from node {node['name']}: {str(e)}")
            return False
    
    def monitor_nodes(self):
        """Monitor all nodes and collect metrics"""
        nodes = self.node_manager.list_nodes()
        metrics = []
        
        for node in nodes:
            # Get node metrics
            node_metrics = self.get_node_metrics(node)
            metrics.append(node_metrics)
            
            # Collect logs if node is online
            if node_metrics['status'] == 'online':
                self.collect_logs(node)
        
        # Save metrics to shared storage
        metrics_dir = self.storage_manager.get_path('logs', 'metrics')
        os.makedirs(metrics_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        metrics_file = os.path.join(metrics_dir, f'metrics_{timestamp}.json')
        
        with open(metrics_file, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        return metrics
    
    def display_node_status(self, metrics):
        """Display node status in a table"""
        table = Table(title="Node Status")
        
        table.add_column("Node", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("CPU Usage", style="yellow")
        table.add_column("Memory Usage", style="yellow")
        table.add_column("Disk Usage", style="yellow")
        table.add_column("Load Avg", style="yellow")
        table.add_column("Workers", style="yellow")
        
        for metric in metrics:
            if metric['status'] == 'online':
                table.add_row(
                    metric['node'],
                    "[green]Online[/green]",
                    f"{metric['cpu_usage']:.1f}%",
                    f"{metric['memory_usage']:.1f}%",
                    f"{metric['disk_usage']:.1f}%",
                    f"{metric['load_avg']:.2f}",
                    str(metric['luigi_workers'])
                )
            else:
                table.add_row(
                    metric['node'],
                    "[red]Offline[/red]",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-"
                )
        
        console.print(table)

def main():
    monitor = MonitoringSystem()
    
    while True:
        try:
            metrics = monitor.monitor_nodes()
            monitor.display_node_status(metrics)
            time.sleep(60)  # Update every minute
        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            time.sleep(60)  # Wait before retrying

if __name__ == "__main__":
    main() 