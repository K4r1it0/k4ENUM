import luigi
from task_classes import TaskExecution, ModuleTask
from rich.console import Console

console = Console()

class WorkflowLoader:
    def __init__(self, config, save_dir):
        self.config = config
        self.save_dir = save_dir
        self.tasks = {}
        self.modules = {}
        
        # Set the loader reference in ModuleTask
        ModuleTask.set_loader(self)
        
        # Load all tasks
        self._load_tasks()
    
    def _load_tasks(self):
        """Load all tasks from the configuration"""
        if 'workflow' not in self.config:
            raise ValueError("No 'workflow' section found in configuration")
        
        workflow = self.config['workflow']
        if 'modules' not in workflow:
            raise ValueError("No 'modules' section found in workflow configuration")
        
        # First pass: Create all task instances
        for module_config in workflow['modules']:
            module_name = module_config['name']
            if 'tasks' not in module_config:
                console.print(f"[yellow]Warning: No tasks found in module {module_name}[/yellow]")
                continue
            
            for task_dict in module_config['tasks']:
                task_name = list(task_dict.keys())[0]
                task_config = task_dict[task_name]
                task_id = f"{module_name}:{task_name}"
                task = TaskExecution(
                    name=task_name,
                    module_name=module_name,
                    config=task_config,
                    save_dir=self.save_dir,
                    args=task_config.get('arguments', {})
                )
                self.tasks[task_id] = task
                TaskExecution._task_registry[f"{module_name}:{task_name}"] = task
        
        # Second pass: Set up dependencies
        for module_config in workflow['modules']:
            module_name = module_config['name']
            if 'tasks' not in module_config:
                continue
                
            for task_dict in module_config['tasks']:
                task_name = list(task_dict.keys())[0]
                task_config = task_dict[task_name]
                task_id = f"{module_name}:{task_name}"
                task = self.tasks[task_id]
                
                if 'requires' in task_config:
                    dependencies = []
                    for dep in task_config['requires']:
                        if ':' in dep:  # Cross-module reference
                            dep_module, dep_task = dep.split(':')
                            dep_id = f"{dep_module}:{dep_task}"
                        else:  # Same module reference
                            dep_id = f"{module_name}:{dep}"
                        
                        if dep_id not in self.tasks:
                            raise ValueError(f"Dependency '{dep_id}' not found for task '{task_id}'")
                        dependencies.append(self.tasks[dep_id])
                    
                    task.dependencies = dependencies
            
            # Create module task
            module_task = ModuleTask(
                name=module_name,
                save_dir=self.save_dir,
                config=module_config
            )
            self.modules[module_name] = module_task
    
    def get_tasks(self):
        """Get all tasks"""
        return list(self.tasks.values())
    
    def get_modules(self):
        """Get all module tasks"""
        return list(self.modules.values())