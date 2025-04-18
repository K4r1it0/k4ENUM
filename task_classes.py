import luigi
import os
import subprocess
import re
from rich.console import Console
from storage_manager import StorageManager

console = Console()

class TaskExecution(luigi.Task):
    """Base Luigi task for task execution"""
    name = luigi.Parameter()
    module_name = luigi.Parameter()
    config = luigi.DictParameter()
    save_dir = luigi.Parameter()
    args = luigi.DictParameter(default={})
    dependencies = luigi.ListParameter(default=[])
    
    # Class variables
    _task_registry = {}
    _storage_manager = None
    
    @classmethod
    def get_storage_manager(cls):
        """Get or create storage manager instance"""
        if cls._storage_manager is None:
            cls._storage_manager = StorageManager()
        return cls._storage_manager
    
    def get_task_id(self):
        """Get unique task identifier"""
        return f"{self.module_name}:{self.name}"
    
    @property
    def task_family(self):
        """Override task family to show module.taskname format"""
        return f"{self.module_name}:{self.name}"
    
    def get_shared_path(self, directory, filename):
        """Get path in shared storage"""
        storage = self.get_storage_manager()
        return storage.get_path(directory, filename)
    
    def _update_status(self, status, output=None):
        """Update task status using file extensions in shared storage"""
        task_id = self.get_task_id()
        storage = self.get_storage_manager()
        
        # Remove any existing status files
        for ext in ['.pending', '.running', '.done', '.failed']:
            status_file = storage.get_path('tasks', f"{task_id}{ext}")
            if os.path.exists(status_file):
                os.remove(status_file)
        
        # Create new status file in shared storage
        status_file = storage.get_path('tasks', f"{task_id}.{status}")
        if output:
            with open(status_file, 'w') as f:
                f.write(output)
        else:
            open(status_file, 'w').close()  # Create empty file
    
    def get_output_path(self, task_ref):
        """Get the output path for a task reference from shared storage"""
        if ":" in task_ref:  # Cross-module reference
            module_name, task_name = task_ref.split(":")
            task = self._task_registry.get(f"{module_name}:{task_name}")
            if task:
                return task.output().path
            # If task not found, construct the path manually
            return self.get_shared_path('tasks', f"{module_name}:{task_name}.done")
        else:  # Same module reference
            task = self._task_registry.get(f"{self.module_name}:{task_ref}")
            if task:
                return task.output().path
            # If task not found, construct the path manually
            return self.get_shared_path('tasks', f"{self.module_name}:{task_ref}.done")
    
    def get_argument_value(self, arg_name):
        """Get argument value with proper precedence"""
        if arg_name in self.args:
            return self.args[arg_name]
        if 'arguments' in self.config and arg_name in self.config['arguments']:
            return self.config['arguments'][arg_name]
        raise ValueError(f"Argument '{arg_name}' not found in any scope")
    
    def run(self):
        """Execute the task"""
        try:
            self._update_status('running')
            
            # Prepare command with arguments
            command = self.config['command']
            if '{' in command and '}' in command:
                # Replace argument placeholders
                for arg_name in re.findall(r'{([^}]+)}', command):
                    arg_value = self.get_argument_value(arg_name)
                    command = command.replace(f"{{{arg_name}}}", str(arg_value))
            
            # Create results directory in shared storage
            results_dir = self.get_shared_path('results', self.get_task_id())
            os.makedirs(results_dir, exist_ok=True)
            
            # Execute command
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=results_dir
            )
            
            # Write output to shared storage
            output_file = self.get_shared_path('results', f"{self.get_task_id()}.output")
            with open(output_file, 'w') as f:
                f.write(f"STDOUT:\n{process.stdout}\n\nSTDERR:\n{process.stderr}")
            
            if process.returncode != 0:
                raise Exception(f"Command failed with exit code {process.returncode}")
            
            # Create done file
            with self.output().open('w') as f:
                f.write(f"Task completed at {results_dir}")
            
            self._update_status('done')
            
        except Exception as e:
            self._update_status('failed', str(e))
            raise
    
    def output(self):
        """Define task output file in shared storage"""
        return luigi.LocalTarget(self.get_shared_path('tasks', f"{self.get_task_id()}.done"))

class ModuleTask(luigi.Task):
    """Container task that represents a single module"""
    name = luigi.Parameter()
    save_dir = luigi.Parameter()
    config = luigi.DictParameter()
    
    # Class variables
    _loader = None
    _storage_manager = None
    
    @classmethod
    def set_loader(cls, loader):
        cls._loader = loader
    
    @classmethod
    def get_storage_manager(cls):
        """Get or create storage manager instance"""
        if cls._storage_manager is None:
            cls._storage_manager = StorageManager()
        return cls._storage_manager
    
    @property
    def task_family(self):
        """Override task family to show actual module name"""
        return self.name
    
    def _update_status(self, status, output=None):
        """Update module status using file extensions in shared storage"""
        storage = self.get_storage_manager()
        
        # Remove any existing status files
        for ext in ['.pending', '.running', '.done', '.failed']:
            status_file = storage.get_path('tasks', f"{self.name}{ext}")
            if os.path.exists(status_file):
                os.remove(status_file)
        
        # Create new status file
        status_file = storage.get_path('tasks', f"{self.name}.{status}")
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
        """Define module output file in shared storage"""
        storage = self.get_storage_manager()
        return luigi.LocalTarget(storage.get_path('tasks', f"{self.name}.done"))