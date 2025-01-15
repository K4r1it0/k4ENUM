#!/usr/bin/env python3
import os
import yaml
import subprocess
from datetime import datetime
from rich.console import Console
from rich.table import Table
from loader import WorkflowLoader
import luigi
import warnings
import argparse
import uuid
from task_classes import ModuleTask, TaskExecution
import json
from node_manager import NodeManager

# Suppress Luigi warnings
warnings.filterwarnings('ignore', category=UserWarning, module='luigi.task')
luigi.interface.core.log_level = 'ERROR'

console = Console()

def show_banner():
    banner = """[cyan]
    ██╗  ██╗██╗  ██╗███████╗███╗   ██╗██╗   ██╗███╗   ███╗
    ██║ ██╔╝██║  ██║██╔════╝████╗  ██║██║   ██║████╗ ████║
    █████╔╝ ███████║█████╗  ██╔██╗ ██║██║   ██║██║ ████╔██║
    ██╔═██╗ ╚════██║██╔══╝  ██║╚██╗██║██║   ██║██║╚██╔╝██║
    ██║  ██╗     ██║██║███╗██║ ╚████║╚███████║██║ ╚═╝ ██║
    ╚═╝  ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝ ╚═╝     ╚═╝
                                                    [/cyan][white]k4ENUM v2.0[/white]"""
    console.print(banner)
    console.print("                [dim cyan]Just another modular domain enumeration framework[/dim cyan]")

def list_workflows():
    """List available workflows"""
    table = Table(title="Available Workflows")
    table.add_column("Workflow", style="cyan")
    table.add_column("Modules", style="green")
    table.add_column("Tasks", style="yellow")
    
    for workflow in os.listdir("workflows"):
        if os.path.isdir(os.path.join("workflows", workflow)):
            config_file = os.path.join("workflows", workflow, "workflow_config.yaml")
            if os.path.exists(config_file):
                with open(config_file) as f:
                    config = yaml.safe_load(f)
                    if config and 'workflow' in config and 'modules' in config['workflow']:
                        modules = []
                        total_tasks = 0
                        for module in config['workflow']['modules']:
                            module_name = module['name']
                            tasks = [list(task.keys())[0] for task in module.get('tasks', [])]
                            if tasks:
                                modules.append(module_name)
                                total_tasks += len(tasks)
                        
                        if modules:
                            table.add_row(
                                workflow,
                                ", ".join(modules),
                                str(total_tasks)
                            )
    
    console.print(table)

def list_nodes():
    """List registered remote nodes"""
    node_manager = NodeManager()
    nodes = node_manager.list_nodes()
    
    if not nodes:
        console.print("[yellow]No remote nodes registered[/yellow]")
        return
    
    table = Table(title="Registered Remote Nodes")
    table.add_column("Name", style="cyan")
    table.add_column("Host", style="green")
    table.add_column("Cores", style="yellow")
    table.add_column("Status", style="magenta")
    
    for node in nodes:
        status = "[green]Connected[/green]" if node_manager.test_connection(node['name']) else "[red]Disconnected[/red]"
        table.add_row(
            node['name'],
            f"{node['host']}:{node['port']}",
            str(node['cores']),
            status
        )
    
    console.print(table)

def register_node(args):
    """Register a new remote node"""
    node_manager = NodeManager()
    success = node_manager.register_node(
        name=args.name,
        host=args.host,
        username=args.username,
        key_file=args.key_file,
        port=args.port,
        cores=args.cores
    )
    if success:
        console.print(f"[green]Successfully registered node {args.name}[/green]")
    else:
        console.print(f"[red]Failed to register node {args.name}[/red]")

def remove_node(args):
    """Remove a registered node"""
    node_manager = NodeManager()
    node_manager.remove_node(args.name)

def main():
    parser = argparse.ArgumentParser(description="k4ENUM - Modular Domain Enumeration Framework")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List workflows command
    list_parser = subparsers.add_parser('list', help='List available workflows')
    
    # Run workflow command
    run_parser = subparsers.add_parser('run', help='Run workflows')
    run_parser.add_argument('-w', '--workflow', nargs='+', required=True, help='Workflow(s) to run')
    run_parser.add_argument('-a', '--args', nargs='+', help='Arguments in key=value format')
    run_parser.add_argument('-c', '--central-scheduler', action='store_true', help='Use central scheduler')
    run_parser.add_argument('-d', '--distributed', action='store_true', help='Enable distributed execution')
    
    # Node management commands
    nodes_parser = subparsers.add_parser('nodes', help='Node management commands')
    node_subparsers = nodes_parser.add_subparsers(dest='node_command', help='Node commands')
    
    # List nodes
    node_list_parser = node_subparsers.add_parser('list', help='List registered nodes')
    
    # Register node
    node_register_parser = node_subparsers.add_parser('register', help='Register a new node')
    node_register_parser.add_argument('name', help='Node name')
    node_register_parser.add_argument('host', help='Node hostname or IP')
    node_register_parser.add_argument('username', help='SSH username')
    node_register_parser.add_argument('key_file', help='Path to SSH private key')
    node_register_parser.add_argument('--port', type=int, default=22, help='SSH port (default: 22)')
    node_register_parser.add_argument('--cores', type=int, help='Number of cores to use (default: auto-detect)')
    
    # Remove node
    node_remove_parser = node_subparsers.add_parser('remove', help='Remove a registered node')
    node_remove_parser.add_argument('name', help='Node name')
    
    args = parser.parse_args()
    
    try:
        show_banner()
        
        if args.command == 'list':
            list_workflows()
            return
        
        elif args.command == 'nodes':
            if args.node_command == 'list':
                list_nodes()
            elif args.node_command == 'register':
                register_node(args)
            elif args.node_command == 'remove':
                remove_node(args)
            return
        
        elif args.command == 'run':
            # Parse workflow arguments
            workflow_args = {}
            if args.args:
                workflow_args.update(dict(arg.split('=', 1) for arg in args.args))
            
            # Create tasks for all workflows
            all_tasks = []
            frameworks = []  # Store framework instances
            for workflow_name in args.workflow:
                # Create and load framework
                framework = Framework(workflow_name)
                frameworks.append(framework)  # Store framework instance
                framework.load()
                
                # Get module tasks
                module_tasks = framework.run_tasks(workflow_args)
                all_tasks.extend(module_tasks)
            
            # Set up distributed execution if enabled
            if args.distributed:
                node_manager = NodeManager()
                nodes = node_manager.list_nodes()
                if not nodes:
                    console.print("[yellow]No remote nodes available. Running locally.[/yellow]")
                else:
                    # Configure Luigi for distributed execution
                    total_cores = node_manager.get_total_cores()
                    luigi.configuration.get_config().set('core', 'parallel-scheduling', 'true')
                    luigi.configuration.get_config().set('core', 'max-workers', str(total_cores))
                    
                    # Set up remote workers
                    for node in nodes:
                        if node_manager.test_connection(node['name']):
                            console.print(f"[green]Using node {node['name']} with {node['cores']} cores[/green]")
                        else:
                            console.print(f"[yellow]Node {node['name']} is not available[/yellow]")
            
            # Run all modules together
            success = luigi.build(
                all_tasks,
                local_scheduler=not args.central_scheduler,
                detailed_summary=True,
                workers=len(all_tasks)  # One worker per task for maximum parallelism
            )
            
            if not success:
                console.print("[red]Some modules failed[/red]")
                for framework in frameworks:
                    framework._update_task_status("failed")
                exit(1)
            
            console.print("[green]All workflows completed successfully![/green]")
            
            # Show results paths
            console.print("\n[cyan]Results locations:[/cyan]")
            for framework in frameworks:
                console.print(f"[green]- {framework.name}:[/green] {framework.save_dir}")
                
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        for framework in frameworks:
            framework._update_task_status("failed")
        exit(1)

if __name__ == "__main__":
    main()