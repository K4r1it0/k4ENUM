import luigi
import os
import subprocess
import re
from rich.console import Console

console = Console()

class TaskExecution(luigi.Task):
    """Base Luigi task for task execution"""
    name = luigi.Parameter()
    module_name = luigi.Parameter()
    config = luigi.DictParameter()
    save_dir = luigi.Parameter()
    args = luigi.DictParameter(default={})
    dependencies = luigi.ListParameter(default=[])
    
    # Class variable to store task instances
    _task_registry = {}
    
    def get_task_id(self):
        """Get unique task identifier"""
        return f"{self.module_name}:{self.name}"
    
    @property
    def task_family(self):
        """Override task family to show module.taskname format"""
        return f"{self.module_name}:{self.name}"
    
    def _update_status(self, status, output=None):
        """Update task status using file extensions"""
        task_id = self.get_task_id()
        # Remove any existing status files
        for ext in ['.pending', '.running', '.done', '.failed']:
            status_file = os.path.join(self.save_dir, f"{task_id}{ext}")
            if os.path.exists(status_file):
                os.remove(status_file)
        
        # Create new status file
        status_file = os.path.join(self.save_dir, f"{task_id}.{status}")
        if output:
            with open(status_file, 'w') as f:
                f.write(output)
        else:
            open(status_file, 'w').close()  # Create empty file
    
    def get_output_path(self, task_ref):
        """Get the output path for a task reference"""
        if ":" in task_ref:  # Cross-module reference
            module_name, task_name = task_ref.split(":")
            task = self._task_registry.get(f"{module_name}:{task_name}")
            if task:
                return task.output().path
            # If task not found, construct the path manually
            return os.path.join(self.save_dir, f"{module_name}:{task_name}.done")
        else:  # Same module reference
            task = self._task_registry.get(f"{self.module_name}:{task_ref}")
            if task:
                return task.output().path
            # If task not found, construct the path manually
            return os.path.join(self.save_dir, f"{self.module_name}:{task_ref}.done")
    
    def get_argument_value(self, arg_name):
        """Get argument value with proper precedence:
        1. Command-line provided args
        2. Task-level arguments
        3. Module-level arguments
        """
        if arg_name in self.args:
            return self.args[arg_name]
        if 'arguments' in self.config and arg_name in self.config['arguments']:
            return self.config['arguments'][arg_name]
        raise ValueError(f"Argument '{arg_name}' not found in any scope")
    
    def output(self):
        # Use .done file for Luigi's completion tracking
        return luigi.LocalTarget(os.path.join(self.save_dir, f"{self.get_task_id()}.done"))
    
    def requires(self):
        # Return dependencies if any
        if self.dependencies:
            # Check if any dependencies are not complete
            incomplete_deps = [dep for dep in self.dependencies if not dep.complete()]
            if incomplete_deps:
                dep_names = [f"{dep.module_name}:{dep.name}" for dep in incomplete_deps]
                # Update status to pending with dependency information
                self._update_status("pending", f"Waiting for dependencies to complete: {', '.join(dep_names)}")
            return self.dependencies
        return []
    
    def run(self):
        try:
            # First check if all dependencies are complete
            deps = self.requires()
            if deps:
                # Wait for all dependencies to complete
                incomplete_deps = [dep for dep in deps if not dep.complete()]
                if incomplete_deps:
                    dep_names = [f"{dep.module_name}:{dep.name}" for dep in incomplete_deps]
                    if self.args.get('verbose'):
                        console.print(f"[yellow]Waiting for dependencies to complete: {', '.join(dep_names)}[/yellow]")
                    yield deps
            
            # Update status to running
            self._update_status("running")
            
            # Regular task execution
            cmd = self.config['command']
            
            # Replace all references in curly braces
            for match in re.finditer(r'\{([^}]+)\}', cmd):
                ref = match.group(1)
                try:
                    # Try to get argument value first
                    value = self.get_argument_value(ref)
                    cmd = cmd.replace(match.group(0), str(value))
                except ValueError:
                    # If not an argument, treat as task output reference
                    output_path = self.get_output_path(ref)
                    cmd = cmd.replace(match.group(0), output_path)
            
            console.print(f"[cyan]Running {self.get_task_id()}[/cyan]")
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            
            # Update status to completed with output
            output_text = result.stdout or result.stderr
            self._update_status("done", output_text)
            
            console.print(f"[green]Completed {self.get_task_id()}[/green]")
                    
        except subprocess.CalledProcessError as e:
            error_output = e.stderr or e.stdout
            self._update_status("failed", error_output.strip())
            if self.args.get('verbose'):
                console.print(f"[red]Error in {self.get_task_id()}: {error_output.strip()}[/red]")
            else:
                console.print(f"[red]Task {self.get_task_id()} failed. Run with -v for details.[/red]")
            raise
        except Exception as e:
            error_msg = str(e)
            self._update_status("failed", error_msg)
            if self.args.get('verbose'):
                error_msg = "[red]Error in {}: {} | Failed command: {}[/red]".format(
                    self.get_task_id(),
                    error_msg.strip().replace('\n', ' '),
                    cmd.strip().replace('\n', ' ')
                )
                console.print(error_msg)
            else:
                console.print(f"[red]Task {self.get_task_id()} failed. Run with -v for details.[/red]")
            raise

class ModuleTask(luigi.Task):
    """Container task that represents a single module"""
    name = luigi.Parameter()
    save_dir = luigi.Parameter()
    config = luigi.DictParameter()
    
    # Class variable to store the loader
    _loader = None
    
    @classmethod
    def set_loader(cls, loader):
        cls._loader = loader
    
    @property
    def task_family(self):
        """Override task family to show actual module name"""
        return self.name
    
    def _update_status(self, status, output=None):
        """Update module status using file extensions"""
        # Remove any existing status files
        for ext in ['.pending', '.running', '.done', '.failed']:
            status_file = os.path.join(self.save_dir, f"{self.name}{ext}")
            if os.path.exists(status_file):
                os.remove(status_file)
        
        # Create new status file
        status_file = os.path.join(self.save_dir, f"{self.name}.{status}")
        with open(status_file, 'w') as f:
            if output:
                f.write(output)
            else:
                f.write(f"Module {self.name} is {status}")
    
    def requires(self):
        # Get all tasks for this module
        tasks = self.get_all_tasks()
        # Return a dictionary of task dependencies
        return {
            task.get_task_id(): task 
            for task in tasks
        }
    
    def get_all_tasks(self):
        # Get all tasks for this module from registry
        return [
            task for key, task in TaskExecution._task_registry.items()
            if key.startswith(f"{self.name}:")
        ]
    
    def output(self):
        return luigi.LocalTarget(os.path.join(self.save_dir, f"{self.name}.done"))
    
    def run(self):
        try:
            # Update status to running
            self._update_status("running")
            
            # Wait for all tasks to complete
            yield self.requires()
            
            # If we get here, all tasks completed successfully
            self._update_status("done", f"Module {self.name} completed successfully")
            
        except Exception as e:
            self._update_status("failed", f"Error: {str(e)}")
            raise