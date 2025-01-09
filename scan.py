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

# Suppress Luigi warnings
warnings.filterwarnings('ignore', category=UserWarning, module='luigi.task')
luigi.interface.core.log_level = 'ERROR'

console = Console()

def show_banner():
    banner = """[cyan]
    ██╗  ██╗██╗  ██╗███████╗███╗   ██╗██╗   ██╗███╗   ███╗
    ██║ ██╔╝██║  ██║██╔════╝████╗  ██║██║   ██║████╗ ████║
    █████╔╝ ███████║█████╗  ██╔██╗ ██║██║   ██║██╔████╔██║
    ██╔═██╗ ╚════██║██╔══╝  ██║╚██╗██║██║   ██║██║╚██╔╝██║
    ██║  ██╗     ██║██║███╗██║ ╚████║╚███████║██║ ╚═╝ ██║
    ╚═╝  ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝ ╚═╝     ╚═╝
                                                    [/cyan][white]k4ENUM v2.0[/white]"""
    console.print(banner)
    console.print("                [dim cyan]Just another modular domain enumeration framework[/dim cyan]")

class Framework:
    def __init__(self, name):
        self.name = name
        self.workflow = {}  # Store workflow configuration
        self.save_dir = self._create_output_dir()
        self.args = {}
        console.print(f"\n[cyan]Results will be saved in:[/cyan] [green]{self.save_dir}[/green]")
    
    def _create_output_dir(self):
        """Create output directory for results"""
        # Create main results directory if it doesn't exist
        if not os.path.exists("results"):
            os.makedirs("results")
            
        # Create workflow directory if it doesn't exist
        workflow_dir = os.path.join("results", self.name)
        if not os.path.exists(workflow_dir):
            os.makedirs(workflow_dir)
            
        # Create scan directory with timestamp
        scan_dir = os.path.join(workflow_dir, f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(scan_dir)
        return scan_dir

    def _update_task_status(self, task_id, status):
        """Update task status using file extensions"""
        # Remove any existing status files
        for ext in ['.pending', '.running', '.done', '.failed']:
            status_file = os.path.join(self.save_dir, f"{task_id}{ext}")
            if os.path.exists(status_file):
                os.remove(status_file)
        
        # Create new status file
        status_file = os.path.join(self.save_dir, f"{task_id}.{status}")
        with open(status_file, 'w') as f:
            f.write(f"Task {task_id} is {status}")

    def load(self):
        """Load workflow configuration"""
        config_file = os.path.join("workflows", self.name, "workflow_config.yaml")
        if os.path.exists(config_file):
            with open(config_file) as f:
                config = yaml.safe_load(f)
                
            if not config or 'workflow' not in config:
                raise ValueError(f"Invalid configuration: 'workflow' section is required")
                
            if 'modules' not in config['workflow']:
                raise ValueError(f"Invalid configuration: 'modules' section is required")
                
            # Store workflow configuration
            self.workflow = config
            
            # Initialize loader with the full config
            self.loader = WorkflowLoader(self.workflow, save_dir=self.save_dir)
            
            # Load modules and their tasks
            for module_config in config['workflow']['modules']:
                if not module_config.get('name'):
                    raise ValueError("Each module must have a name")
                    
                if 'tasks' not in module_config:
                    raise ValueError(f"Module '{module_config['name']}' has no tasks")
                    
                for task_dict in module_config['tasks']:
                    # Each task is a dictionary with a single key (task name) and value (task config)
                    task_name = list(task_dict.keys())[0]
                    task_config = task_dict[task_name]
                    
                    # Add name to task config
                    task_config['name'] = task_name
                    
                    # Validate task configuration
                    if not self._validate_task_config(task_config):
                        raise ValueError(f"Invalid configuration for task '{task_name}'")
                    
                    # Create pending status file for the task
                    task_id = f"{module_config['name']}:{task_name}"
                    self._update_task_status(task_id, "pending")
            
            self.modules = self.loader.get_modules()
        else:
            raise ValueError(f"No workflow configuration found for '{self.name}'")

    def _validate_task_config(self, config):
        """Validate task configuration"""
        # Check if task has a command
        if 'command' not in config:
            return False
            
        return True

    def validate_args(self, args):
        """Validate all required arguments are provided"""
        missing_args = {}
        
        # Extract arguments from command strings
        for module_config in self.workflow['workflow']['modules']:
            module_name = module_config['name']
            for task_dict in module_config['tasks']:
                task_name = list(task_dict.keys())[0]
                task_config = task_dict[task_name]
                command = task_config['command']
                
                # Find all arguments in {arg} format
                import re
                arg_matches = re.findall(r'\{([^:}]+)\}', command)
                for arg_name in arg_matches:
                    if ':' not in arg_name and arg_name not in args:
                        if arg_name not in missing_args:
                            missing_args[arg_name] = []
                        missing_args[arg_name].append(f"{module_name}:{task_name}")
        
        if missing_args:
            error_msg = "\nMissing required arguments:"
            for arg, tasks in missing_args.items():
                error_msg += f"\n  - {arg} (required by: {', '.join(tasks)})"
            raise ValueError(error_msg)

    def run_tasks(self, args=None):
        """Create module tasks without running them"""
        if args is None:
            args = {}
            
        self.args = args
        # Validate arguments before starting
        try:
            self.validate_args(args)
            
            # Set the loader for ModuleTask
            ModuleTask.set_loader(self.loader)
            
            module_tasks = []
            task_configs = {}  # Store task configs for dependency checking
            
            # First pass: Create all tasks and store their configs
            for module_config in self.workflow['workflow']['modules']:
                module_name = module_config['name']
                for task_dict in module_config['tasks']:
                    task_name = list(task_dict.keys())[0]
                    task_config = task_dict[task_name]
                    task_id = f"{module_name}:{task_name}"
                    task_configs[task_id] = task_config
                    
                    # Initially mark all tasks as pending
                    self._update_task_status(task_id, "pending")
            
            # Second pass: Update pending status with dependency information
            for task_id, config in task_configs.items():
                if 'requires' in config:
                    requires = config['requires'] if isinstance(config['requires'], list) else [config['requires']]
                    # Format the dependency list for the message
                    dep_list = [dep if ':' in dep else f"{task_id.split(':')[0]}:{dep}" for dep in requires]
                    # Update the pending status with dependency information
                    status_file = os.path.join(self.save_dir, f"{task_id}.pending")
                    with open(status_file, 'w') as f:
                        f.write(f"Waiting for dependencies to complete: {', '.join(dep_list)}")
            
            # Create all module tasks
            for module_config in self.workflow['workflow']['modules']:
                module_name = module_config['name']
                # Create the module container
                module_task = ModuleTask(
                    name=module_name,
                    save_dir=self.save_dir,
                    config=module_config
                )
                
                # Create and register task executions
                for task_dict in module_config['tasks']:
                    task_name = list(task_dict.keys())[0]
                    task_config = task_dict[task_name]
                    task_config['name'] = task_name  # Ensure name is in config
                    
                    task_execution = TaskExecution(
                        name=task_name,
                        module_name=module_name,
                        config=task_config,
                        save_dir=self.save_dir,
                        args=args
                    )
                    TaskExecution._task_registry[f"{module_name}:{task_name}"] = task_execution
                
                module_tasks.append(module_task)
            
            # Set up dependencies after all tasks exist
            for module_config in self.workflow['workflow']['modules']:
                module_name = module_config['name']
                for task_dict in module_config['tasks']:
                    task_name = list(task_dict.keys())[0]
                    task_config = task_dict[task_name]
                    
                    if 'requires' in task_config:
                        task_exec = TaskExecution._task_registry[f"{module_name}:{task_name}"]
                        deps = []
                        requires = task_config['requires'] if isinstance(task_config['requires'], list) else [task_config['requires']]
                        
                        for dep in requires:
                            if ':' in dep:
                                # Cross-module dependency
                                deps.append(TaskExecution._task_registry[dep])
                            else:
                                # Same module dependency
                                deps.append(TaskExecution._task_registry[f"{module_name}:{dep}"])
                        
                        task_exec.dependencies = deps
            
            return module_tasks
        except Exception as e:
            for module_config in self.workflow['workflow']['modules']:
                for task_dict in module_config['tasks']:
                    task_name = list(task_dict.keys())[0]
                    task_id = f"{module_config['name']}:{task_name}"
                    self._update_task_status(task_id, "failed")
            raise

def list_workflows():
    """List available workflows"""
    table = Table()
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
                        for module in config['workflow']['modules']:
                            module_name = module['name']
                            tasks = [list(task.keys())[0] for task in module.get('tasks', [])]
                            if tasks:
                                table.add_row(workflow, module_name, ", ".join(sorted(tasks)))
    
    console.print("\n[bold cyan]Available Workflows[/bold cyan]")
    console.print(table)

def main():
    parser = argparse.ArgumentParser(description='Modular domain enumeration framework')
    parser.add_argument('-w', '--workflow', help='Workflow to run', nargs='+')
    parser.add_argument('-l', '--list', action='store_true', help='List workflows')
    parser.add_argument('-a', '--args', nargs='+', help='Arguments (key=value)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-c', action='store_true', help='Use central Luigi scheduler')
    args = parser.parse_args()
    
    show_banner()
    
    if args.list:
        list_workflows()
        return
    
    if not args.workflow:
        console.print("[red]Error: Please specify at least one workflow (-w)[/red]")
        return
    
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
            
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        for framework in frameworks:
            framework._update_task_status("failed")
        exit(1)

if __name__ == "__main__":
    main()