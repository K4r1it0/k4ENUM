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

def setup_luigi_config(use_central_scheduler=False, distributed=False):
    """Setup Luigi configuration based on command-line arguments"""
    # Load template configuration
    template_path = "luigi.cfg.template"
    if os.path.exists(template_path):
        with open(template_path) as f:
            config_text = f.read()
    else:
        # Default configuration if template doesn't exist
        config_text = """[core]
parallel-scheduling=true

[scheduler]
record_task_history=true
remove_delay=1800
retry_delay=300
state-path=/tmp/luigi-state.pickle

[worker]
keep_alive=true
ping_interval=20
wait_interval=20
max_reschedules=3
timeout=3600

[retcode]
already_running=10
missing_data=20
not_run=25
task_failed=30
scheduling_error=35
unhandled_exception=40"""
    
    # Create temporary config file
    config_path = "luigi.cfg"
    with open(config_path, 'w') as f:
        if use_central_scheduler:
            # Add central scheduler configuration
            f.write("[core]\n")
            f.write("default-scheduler-host=localhost\n")
            f.write("default-scheduler-port=8082\n")
            f.write("parallel-scheduling=true\n\n")
        f.write(config_text)
    
    # Load configuration into Luigi
    luigi.configuration.LuigiConfigParser.reload()

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
    parser = argparse.ArgumentParser(description='Modular domain enumeration framework')
    parser.add_argument('-w', '--workflow', help='Workflow to run', nargs='+')
    parser.add_argument('-l', '--list', action='store_true', help='List workflows')
    parser.add_argument('-a', '--args', nargs='+', help='Arguments (key=value)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-c', action='store_true', help='Use central Luigi scheduler')
    parser.add_argument('-d', '--distributed', action='store_true', help='Enable distributed execution')
    
    # Node management arguments
    node_group = parser.add_argument_group('Node management')
    node_group.add_argument('--nodes', choices=['list', 'register', 'remove'], help='Node management commands')
    node_group.add_argument('--name', help='Node name for register/remove commands')
    node_group.add_argument('--host', help='Node hostname/IP for register command')
    node_group.add_argument('--username', help='SSH username for register command')
    node_group.add_argument('--key-file', help='SSH private key file for register command')
    node_group.add_argument('--port', type=int, default=22, help='SSH port for register command (default: 22)')
    node_group.add_argument('--cores', type=int, help='Number of cores to use (default: auto-detect)')
    
    args = parser.parse_args()
    
    try:
        show_banner()
        
        if args.list:
            list_workflows()
            return
        
        if args.nodes:
            if args.nodes == 'list':
                list_nodes()
            elif args.nodes == 'register':
                if not all([args.name, args.host, args.username, args.key_file]):
                    console.print("[red]Error: register command requires --name, --host, --username, and --key-file[/red]")
                    return
                register_node(args)
            elif args.nodes == 'remove':
                if not args.name:
                    console.print("[red]Error: remove command requires --name[/red]")
                    return
                remove_node(args)
            return
        
        if not args.workflow:
            console.print("[red]Error: Please specify at least one workflow (-w)[/red]")
            return
        
        # Setup Luigi configuration
        setup_luigi_config(args.c, args.distributed)
        
        try:
            # Parse arguments
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
                local_scheduler=not args.c,
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
                
        finally:
            # Cleanup temporary Luigi config
            if os.path.exists("luigi.cfg"):
                os.remove("luigi.cfg")
                
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        for framework in frameworks:
            framework._update_task_status("failed")
        # Cleanup temporary Luigi config
        if os.path.exists("luigi.cfg"):
            os.remove("luigi.cfg")
        exit(1)

if __name__ == "__main__":
    main()