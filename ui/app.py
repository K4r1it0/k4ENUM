# app.py
from flask import Flask, render_template, jsonify, request, Response, redirect, make_response
from flask_cors import CORS
import yaml
import os
import logging
from pathlib import Path
import subprocess
import threading
import queue
import json
import sys
from datetime import datetime
import time

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.DEBUG)

# Get the project root directory (one level up from ui directory)
PROJECT_ROOT = Path(__file__).parent.parent
# Set workflows directory relative to project root
WORKFLOWS_DIR = PROJECT_ROOT / "workflows"
WORKFLOWS_DIR.mkdir(exist_ok=True)
EXECUTIONS_DIR = PROJECT_ROOT / "results"

# Store task status
task_status = {}
task_output = {}

logging.debug(f"Project root: {PROJECT_ROOT.absolute()}")
logging.debug(f"Workflows directory: {WORKFLOWS_DIR.absolute()}")

def format_timestamp(timestamp):
    """Format timestamp from YYYYMMDD_HHMMSS to a readable format"""
    try:
        # Remove 'scan_' prefix if present
        if timestamp.startswith('scan_'):
            timestamp = timestamp[5:]
        
        # Parse the timestamp
        if '_' in timestamp:
            date_part = timestamp[:8]
            time_part = timestamp[9:]
        else:
            date_part = timestamp[:8]
            time_part = timestamp[8:]
        
        # Convert to datetime object
        year = date_part[:4]
        month = date_part[4:6]
        day = date_part[6:8]
        hour = time_part[:2]
        minute = time_part[2:4]
        second = time_part[4:6]
        
        from datetime import datetime
        dt = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
        
        # Get current time
        now = datetime.now()
        diff = now - dt
        
        # If less than 24 hours ago, show relative time
        if diff.days < 1:
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            if hours > 0:
                return f"{hours}h {minutes}m ago"
            elif minutes > 0:
                return f"{minutes}m ago"
            else:
                return "Just now"
        # If this year, omit the year
        elif dt.year == now.year:
            return dt.strftime("%b %d, %H:%M")
        # Otherwise show full date
        else:
            return dt.strftime("%b %d %Y, %H:%M")
            
    except Exception as e:
        print(f"Error formatting timestamp: {e}")
        return timestamp

@app.route('/')
def index():
    """Serve the dashboard page"""
    stats = {
        'total_workflows': len(list(WORKFLOWS_DIR.glob('*'))),
        'total_executions': 0,
        'running_executions': 0,
        'failed_executions': 0,
    }
    
    # Get execution statistics
    try:
        executions = get_executions()
        stats['total_executions'] = len(executions)
        stats['running_executions'] = len([e for e in executions if e['status'].lower() == 'running'])
        stats['failed_executions'] = len([e for e in executions if e['status'].lower() == 'failed'])
        
        # Get only the 5 most recent executions
        recent_executions = executions[:5]
    except Exception as e:
        logging.error(f"Error getting execution stats: {e}")
        recent_executions = []
    
    return render_template('dashboard.html', stats=stats, recent_executions=recent_executions)

@app.route('/editor')
def editor():
    """Serve the workflow editor page"""
    workflow_name = request.args.get('workflow')
    return render_template('editor.html', workflow_name=workflow_name)

@app.route('/workflows')
def workflows():
    """Serve the workflows listing page"""
    workflows = []
    try:
        WORKFLOWS_DIR.mkdir(exist_ok=True)
        # Scan through all subdirectories in WORKFLOWS_DIR
        for workflow_dir in WORKFLOWS_DIR.iterdir():
            if workflow_dir.is_dir():
                # Look for workflow config files in each directory
                for config_file in workflow_dir.glob("*.yaml"):
                    try:
                        with open(config_file) as f:
                            config = yaml.safe_load(f)
                            workflows.append({
                                'name': workflow_dir.name,
                                'config': config
                            })
                    except Exception as e:
                        logging.error(f"Error loading {config_file}: {e}")
                        continue
    except Exception as e:
        logging.error(f"Error listing workflows: {e}")

    return render_template('index.html', workflows=workflows)

@app.route('/api/workflows', methods=['GET'])
def list_workflows():
    """List all available workflows"""
    workflows = []
    try:
        WORKFLOWS_DIR.mkdir(exist_ok=True)
        logging.debug(f"Scanning directory: {WORKFLOWS_DIR.absolute()}")
        
        # Scan through all subdirectories in WORKFLOWS_DIR
        for workflow_dir in WORKFLOWS_DIR.iterdir():
            if workflow_dir.is_dir():
                logging.debug(f"Found workflow directory: {workflow_dir}")
                # Look for workflow config files in each directory
                for config_file in workflow_dir.glob("*.yaml"):
                    try:
                        logging.debug(f"Found config file: {config_file}")
                        with open(config_file) as f:
                            config = yaml.safe_load(f)
                            workflows.append({
                                'name': workflow_dir.name,
                                'config': config
                            })
                            logging.debug(f"Successfully loaded workflow: {workflow_dir.name}")
                    except Exception as e:
                        logging.error(f"Error loading {config_file}: {e}")
                        continue
        
        return jsonify(workflows)
    except Exception as e:
        logging.error(f"Error listing workflows: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/workflow/<name>', methods=['GET'])
def get_workflow(name):
    """Get a specific workflow configuration"""
    workflow_dir = WORKFLOWS_DIR / name
    logging.debug(f"Looking for workflow in directory: {workflow_dir}")
    
    if workflow_dir.exists() and workflow_dir.is_dir():
        try:
            config_files = list(workflow_dir.glob("*.yaml"))
            if not config_files:
                logging.error(f"No config files found in {workflow_dir}")
                return jsonify({'error': 'No configuration file found'}), 404
                
            config_file = config_files[0]
            logging.debug(f"Using config file: {config_file}")
            
            with open(config_file) as f:
                # Store the original YAML string
                yaml_str = f.read()
                # Parse the YAML for the config
                config = yaml.safe_load(yaml_str)
                
                # Ensure requires is an array in all tasks
                if 'config' in config and 'workflow' in config['config'] and 'modules' in config['config']['workflow']:
                    for module in config['config']['workflow']['modules']:
                        if 'tasks' in module:
                            for task_obj in module['tasks']:
                                for task_name, task_config in task_obj.items():
                                    if 'requires' in task_config:
                                        task_config['requires'] = (
                                            task_config['requires'] 
                                            if isinstance(task_config['requires'], list) 
                                            else [task_config['requires']]
                                        )
                
                return jsonify({
                    'name': name, 
                    'config': config,
                    'yaml': yaml_str
                })
        except Exception as e:
            logging.error(f"Error loading workflow {name}: {e}")
            return jsonify({'error': str(e)}), 400
    
    return jsonify({'error': 'Workflow not found'}), 404

@app.route('/api/workflow/diagram/<name>', methods=['GET'])
def get_workflow_diagram(name):
    """Get workflow as Mermaid diagram"""
    workflow_dir = WORKFLOWS_DIR / name
    if workflow_dir.exists() and workflow_dir.is_dir():
        try:
            config_files = list(workflow_dir.glob("*.yaml"))
            if not config_files:
                return jsonify({'error': 'No configuration file found'}), 404
                
            config_file = config_files[0]
            with open(config_file) as f:
                config = yaml.safe_load(f)
                
                # Generate Mermaid diagram
                mermaid_code = "flowchart TD\n"
                
                # Handle the tasks
                tasks = config.get('tasks', [])
                for task in tasks:
                    if isinstance(task, dict):
                        for task_name, task_config in task.items():
                            # Add node
                            safe_name = task_name.replace(' ', '_').replace('-', '_')
                            mermaid_code += f'    {safe_name}["{task_name}"]\n'
                            
                            # Add edges from requirements
                            if 'requires' in task_config:
                                for req in task_config['requires']:
                                    safe_req = req.replace(' ', '_').replace('-', '_')
                                    mermaid_code += f'    {safe_req} --> {safe_name}\n'
                
                # Add styling
                mermaid_code += '\n    classDef default fill:#f9f9f9,stroke:#333,stroke-width:1px;\n'
                
                return jsonify({'diagram': mermaid_code})
                
        except Exception as e:
            logging.error(f"Error generating diagram for {name}: {e}")
            return jsonify({'error': str(e)}), 400
            
    return jsonify({'error': 'Workflow not found'}), 404

@app.route('/api/workflow/<name>', methods=['POST'])
def save_workflow(name):
    """Save or update a workflow configuration"""
    try:
        workflow_dir = WORKFLOWS_DIR / name
        workflow_dir.mkdir(exist_ok=True)
        
        workflow_path = workflow_dir / "workflow_config.yaml"
        logging.debug(f"Saving workflow to: {workflow_path}")
        
        # Get the raw YAML content from the request
        yaml_content = request.get_data(as_text=True)
        
        # Validate that it's valid YAML and ensure requires is an array
        try:
            config = yaml.safe_load(yaml_content)
            
            # Ensure requires is an array in all tasks
            if 'config' in config and 'workflow' in config['config'] and 'modules' in config['config']['workflow']:
                for module in config['config']['workflow']['modules']:
                    if 'tasks' in module:
                        for task_obj in module['tasks']:
                            for task_name, task_config in task_obj.items():
                                if 'requires' in task_config:
                                    task_config['requires'] = (
                                        task_config['requires'] 
                                        if isinstance(task_config['requires'], list) 
                                        else [task_config['requires']]
                                    )
            
            # Re-dump the YAML with the formatted requires
            yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False)
            
        except yaml.YAMLError as e:
            return jsonify({'error': f'Invalid YAML format: {str(e)}'}), 400
        
        # Write the YAML content to the file
        with open(workflow_path, 'w') as f:
            f.write(yaml_content)
            
        logging.debug(f"Successfully saved workflow: {name}")
        return jsonify({'message': 'Workflow saved successfully'})
    except Exception as e:
        logging.error(f"Error saving workflow {name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/workflow/<name>/init', methods=['POST'])
def init_workflow(name):
    """Initialize a new workflow with template configuration"""
    try:
        data = request.json
        if not data or 'template' not in data:
            return jsonify({'error': 'No template configuration provided'}), 400

        workflow_dir = WORKFLOWS_DIR / name
        if workflow_dir.exists():
            return jsonify({'error': 'Workflow already exists'}), 409

        # Create workflow directory
        workflow_dir.mkdir(exist_ok=True)
        
        # Create workflow config file
        workflow_path = workflow_dir / "workflow_config.yaml"
        logging.debug(f"Creating workflow at: {workflow_path}")
        
        # Configure YAML dumper to maintain order
        class OrderedDumper(yaml.SafeDumper):
            pass
        
        def dict_representer(dumper, data):
            return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
        
        OrderedDumper.add_representer(dict, dict_representer)
        
        with open(workflow_path, 'w') as f:
            yaml.dump(data['template'], f, Dumper=OrderedDumper, default_flow_style=False, sort_keys=False)
            
        logging.debug(f"Successfully initialized workflow: {name}")
        return jsonify({'message': 'Workflow initialized successfully'})
    except Exception as e:
        logging.error(f"Error initializing workflow {name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/workflow/<name>/run', methods=['POST'])
def run_workflow(name):
    """Run a workflow with given arguments"""
    try:
        args = request.json.get('args', {})
        
        # Get list of existing scans before starting new one
        workflow_exec_dir = os.path.join(EXECUTIONS_DIR, name)
        existing_scans = set()
        if os.path.exists(workflow_exec_dir):
            existing_scans = set(os.listdir(workflow_exec_dir))
        
        # Convert args to command line format
        arg_list = [f"{k}={v}" for k, v in args.items()]
        
        # Create the bash command that sources venv and runs the script
        bash_cmd = [
            "bash",
            "-c",
            f"cd {PROJECT_ROOT} && source venv/bin/activate && python3 scan.py -c -w {name} {' '.join(['-a'] + arg_list) if arg_list else ''}"
        ]
        print(bash_cmd)
        # Start the process
        process = subprocess.Popen(
            bash_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        
        # Wait a short time for the scan directory to be created
        time.sleep(2)
        
        # Check for new scan directory
        if os.path.exists(workflow_exec_dir):
            current_scans = set(os.listdir(workflow_exec_dir))
            new_scans = current_scans - existing_scans
            if new_scans:
                # Get the newest scan directory
                scan_id = max(new_scans)
                return jsonify({
                    'scan_id': scan_id
                })
        
        # If no scan directory found, check process output for errors
        stdout, stderr = process.communicate(timeout=1)
        if stderr:
            raise Exception(f"Workflow failed to start: {stderr}")
            
        raise Exception("Could not find new scan directory")
        
    except Exception as e:
        logging.error(f"Error running workflow {name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/workflow/new')
def new_workflow():
    """Serve the workflow editor page for a new workflow"""
    return render_template('editor.html', workflow_name=None)

@app.route('/workflow/<name>/edit')
def edit_workflow(name):
    """Serve the workflow editor page for a specific workflow"""
    try:
        workflow_dir = WORKFLOWS_DIR / name.lower()
        if not workflow_dir.exists():
            return redirect('/workflow/new')
        return render_template('editor.html', workflow_name=name)
    except Exception as e:
        logging.error(f"Error accessing workflow {name}: {e}")
        return redirect('/workflow/new')

@app.route('/workflow/<n>')
def view_workflow(name):
    """Serve the workflow view/run page for a specific workflow"""
    try:
        workflow_dir = WORKFLOWS_DIR / name.lower()
        if not workflow_dir.exists():
            return redirect('/')
            
        # Get workflow configuration
        config_files = list(workflow_dir.glob("*.yaml"))
        if not config_files:
            return redirect('/')
            
        config_file = config_files[0]
        with open(config_file) as f:
            # Parse and re-dump the YAML to ensure proper formatting
            config = yaml.safe_load(f)
            yaml_str = yaml.dump(config, default_flow_style=False, sort_keys=False)
            
        return render_template('workflow_view.html',
                             workflow_name=name,
                             yaml_content=yaml_str,
                             is_execution_view=False)
    except Exception as e:
        logging.error(f"Error accessing workflow {name}: {e}")
        return redirect('/')

@app.route('/executions')
def executions():
    """Serve the executions page"""
    try:
        executions_list = get_executions()
        # Get unique workflow names for the filter
        workflows = list(set(e['workflow_name'] for e in executions_list if e.get('workflow_name')))
    except Exception as e:
        logging.error(f"Error getting executions: {e}")
        executions_list = []
        workflows = []
    
    return render_template('executions.html', executions=executions_list, workflows=workflows)
@app.route('/api/executions')
def get_executions():
    """Helper function to get executions with proper formatting"""
    executions = []
    try:
        EXECUTIONS_DIR.mkdir(exist_ok=True)
        for workflow_dir in EXECUTIONS_DIR.iterdir():
            if workflow_dir.is_dir():
                # Get workflow configuration to count tasks
                workflow_name = workflow_dir.name
                workflow_config_file = WORKFLOWS_DIR / workflow_name / "workflow_config.yaml"
                task_count = 0
                
                if workflow_config_file.exists():
                    try:
                        with open(workflow_config_file) as f:
                            config = yaml.safe_load(f)
                            # Count tasks from all modules
                            if 'workflow' in config and 'modules' in config['workflow']:
                                for module in config['workflow']['modules']:
                                    if 'tasks' in module:
                                        task_count += len(module['tasks'])
                    except Exception as e:
                        logging.error(f"Error reading workflow config {workflow_config_file}: {e}")
                
                for scan_dir in workflow_dir.iterdir():
                    if scan_dir.is_dir():
                        try:
                            # Parse the timestamp from directory name
                            scan_id = scan_dir.name
                            timestamp = scan_id.replace('scan_', '')
                            
                            # Determine status from task files
                            task_files = [f for f in os.listdir(scan_dir) if ':' in f]
                            status = 'pending'
                            if any(f.endswith('.running') for f in task_files):
                                status = 'running'
                            elif any(f.endswith('.failed') for f in task_files):
                                status = 'failed'
                            elif task_files and all(f.endswith('.done') for f in task_files):
                                status = 'completed'
                            
                            executions.append({
                                'id': scan_id,
                                'status': status,
                                'timestamp': timestamp,
                                'workflow': workflow_name,
                                'task_count': task_count
                            })
                        except Exception as e:
                            logging.error(f"Error processing execution {scan_dir}: {e}")
                            continue
        
        # Sort executions by timestamp (newest first)
        executions.sort(key=lambda x: x['timestamp'], reverse=True)
    except Exception as e:
        logging.error(f"Error listing executions: {e}")
    
    return executions

@app.route('/workflow/<workflow_name>/execution/<scan_id>')
def view_execution(workflow_name, scan_id):
    try:
        # Get workflow configuration
        workflow_file = os.path.join(WORKFLOWS_DIR, f"{workflow_name}/workflow_config.yaml")
        print(workflow_file)
        if not os.path.exists(workflow_file):
            return "Workflow not found", 404

        # Read raw YAML content
        with open(workflow_file, 'r') as f:
            yaml_content = f.read()
            workflow_config = yaml.safe_load(yaml_content)

        # Get execution directory
        execution_dir = os.path.join(EXECUTIONS_DIR, workflow_name, scan_id)
        if not os.path.exists(execution_dir):
            return "Execution not found", 404

        # Parse the timestamp from scan_id (format: scan_YYYYMMDD_HHMMSS)
        timestamp_str = scan_id.replace('scan_', '')
        start_time = timestamp_str  # Let client format the timestamp

        # Get tasks and their status
        tasks = []
        task_map = {}  # Map task names to their status
        for task_file in os.listdir(execution_dir):
            task_name = task_file.rsplit('.', 1)[0]
            if ":" not in task_name:
                continue
                
            # Determine task status
            status = "pending"
            if task_file.endswith('.running'):
                status = "running"
            elif task_file.endswith('.failed'):
                status = "failed"
            elif task_file.endswith('.done'):
                status = "completed"

            tasks.append({
                "name": task_name,
                "status": status
            })
            task_map[task_name] = status

        # Create workflow visualization data
        nodes = []
        edges = []
        node_id = 1
        node_map = {}  # Map task names to node IDs

        # Create nodes for each task in the workflow
        if 'workflow' in workflow_config and 'modules' in workflow_config['workflow']:
            for module in workflow_config['workflow']['modules']:
                if 'tasks' in module:
                    for task_dict in module['tasks']:
                        task_name = list(task_dict.keys())[0]
                        task_id = f"{module['name']}:{task_name}"
                        
                        # Create node
                        node_map[task_id] = node_id
                        nodes.append({
                            "id": node_id,
                            "label": task_id,
                            "status": task_map.get(task_id, "pending")
                        })
                        node_id += 1

                        # Create edges based on dependencies
                        task_config = task_dict[task_name]
                        if 'requires' in task_config:
                            for req in task_config['requires']:
                                req_id = f"{module['name']}:{req}"
                                if req_id in node_map:
                                    edges.append({
                                        "from": node_map[req_id],
                                        "to": node_map[task_id]
                                    })

        workflow_data = {
            "nodes": nodes,
            "edges": edges
        }

        return render_template('workflow_view.html',
                             workflow_name=workflow_name,
                             scan_id=scan_id,
                             workflow_config=workflow_config,
                             yaml_content=yaml_content,
                             workflow_data=workflow_data,
                             tasks=tasks,
                             start_time=start_time)

    except Exception as e:
        app.logger.error(f"Error viewing execution: {str(e)}")
        return str(e), 500

@app.route('/api/workflow/<workflow_name>/execution/<scan_id>/details')
def get_execution_details(workflow_name, scan_id):
    try:
        execution_dir = os.path.join(EXECUTIONS_DIR, workflow_name, scan_id)
        if not os.path.exists(execution_dir):
            return jsonify({"error": "Execution not found"}), 404

        tasks = []
        for task_file in os.listdir(execution_dir):
            task_name = task_file.rsplit('.', 1)[0]
            # Determine task status
            status = "pending"
            if task_file.endswith('.running'):
                status = "running"
            elif task_file.endswith('.failed'):
                status = "failed"
            elif task_file.endswith('.done'):
                status = "done"


            if ":" in task_name:
                tasks.append({
                "name": task_name,
                "status": status,
            })

        # Get overall status
        status = "pending"
        if any(t["status"] == "running" for t in tasks):
            status = "running"
        elif any(t["status"] == "failed" for t in tasks):
            status = "failed"
        elif all(t["status"] == "done" for t in tasks):
            status = "completed"

        return jsonify({
            "status": status,
            "tasks": tasks
        })

    except Exception as e:
        app.logger.error(f"Error getting execution details: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/workflow', methods=['POST'])
def create_workflow():
    """Create a new workflow"""
    try:
        data = request.json
        if not data or 'name' not in data or 'yaml' not in data:
            return jsonify({'error': 'Missing required fields (name, yaml)'}), 400

        name = data['name']
        yaml_content = data['yaml']
        
        # Create workflow directory
        workflow_dir = WORKFLOWS_DIR / name
        workflow_dir.mkdir(exist_ok=True)
        
        workflow_path = workflow_dir / "workflow_config.yaml"
        logging.debug(f"Creating workflow at: {workflow_path}")
        
        # Write the YAML content directly to the file
        with open(workflow_path, 'w') as f:
            f.write(yaml_content)
            
        logging.debug(f"Successfully created workflow: {name}")
        return jsonify({'message': 'Workflow created successfully'})
    except Exception as e:
        logging.error(f"Error creating workflow: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/workflow/<name>', methods=['PUT'])
def update_workflow(name):
    """Update an existing workflow configuration"""
    try:
        data = request.json
        if not data or 'yaml' not in data:
            return jsonify({'error': 'No YAML content provided'}), 400
            
        workflow_dir = WORKFLOWS_DIR / name
        workflow_dir.mkdir(exist_ok=True)
        
        workflow_path = workflow_dir / "workflow_config.yaml"
        logging.debug(f"Updating workflow at: {workflow_path}")
        
        # Write the YAML content directly to the file
        with open(workflow_path, 'w') as f:
            f.write(data['yaml'])
            
        logging.debug(f"Successfully updated workflow: {name}")
        return jsonify({'message': 'Workflow updated successfully'})
    except Exception as e:
        logging.error(f"Error updating workflow {name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/arrow-test')
def arrow_test():
    return render_template('arrow_test.html')

@app.route('/workflow/<workflow_name>/execution/<scan_id>/results')
def view_execution_results(workflow_name, scan_id):
    """View all task results for a specific execution"""
    try:
        execution_dir = os.path.join(EXECUTIONS_DIR, workflow_name, scan_id)
        if not os.path.exists(execution_dir):
            return jsonify({"error": "Execution not found"}), 404

        task_results = []
        for task_file in os.listdir(execution_dir):
            if not any(task_file.endswith(ext) for ext in ['.done', '.failed', '.running', '.pending']):
                continue
                
            task_name = task_file.rsplit('.', 1)[0]
            status = task_file.rsplit('.', 1)[1]
            
            # Read file content if it's done or failed
            content = ""
            if status in ['done', 'failed']:
                try:
                    with open(os.path.join(execution_dir, task_file), 'r') as f:
                        content = f.read()
                except Exception as e:
                    content = f"Error reading file: {str(e)}"
            
            task_results.append({
                "name": task_name,
                "status": status,
                "content": content,
                "size": os.path.getsize(os.path.join(execution_dir, task_file))
            })
        
        return render_template('execution_results.html',
                             workflow_name=workflow_name,
                             scan_id=scan_id,
                             task_results=task_results)
                             
    except Exception as e:
        app.logger.error(f"Error viewing execution results: {str(e)}")
        return str(e), 500

@app.route('/workflow/<workflow_name>/execution/<scan_id>/<task_name>')
def view_task_result(workflow_name, scan_id, task_name):
    """View result for a specific task"""
    try:
        execution_dir = os.path.join(EXECUTIONS_DIR, workflow_name, scan_id)
        if not os.path.exists(execution_dir):
            return jsonify({"error": "Execution not found"}), 404
            
        # Find the task file with any status extension
        task_file = None
        task_status = None
        for ext in ['.done', '.failed', '.running', '.pending']:
            potential_file = f"{task_name}{ext}"
            if os.path.exists(os.path.join(execution_dir, potential_file)):
                task_file = potential_file
                task_status = ext[1:]  # Remove the dot
                break
                
        if not task_file:
            return jsonify({"error": "Task not found"}), 404
            
        # Read file content if it's done or failed
        content = ""
        if task_status in ['done', 'failed']:
            try:
                with open(os.path.join(execution_dir, task_file), 'r') as f:
                    content = f.read()
            except Exception as e:
                content = f"Error reading file: {str(e)}"
                
        file_size = os.path.getsize(os.path.join(execution_dir, task_file))
        
        return render_template('task_result.html',
                             workflow_name=workflow_name,
                             scan_id=scan_id,
                             task_name=task_name,
                             status=task_status,
                             content=content,
                             file_size=file_size)
                             
    except Exception as e:
        app.logger.error(f"Error viewing task result: {str(e)}")
        return str(e), 500

def get_task_result(workflow_name, scan_id, task_name):
    """Get the result of a specific task from a workflow execution."""
    try:
        # Get the workflow execution directory
        execution_dir = os.path.join(EXECUTIONS_DIR, workflow_name, scan_id)
        if not os.path.exists(execution_dir):
            return None

        # Find the task file with any status extension
        task_file = None
        for ext in ['.done', '.failed', '.running', '.pending']:
            potential_file = f"{task_name}{ext}"
            if os.path.exists(os.path.join(execution_dir, potential_file)):
                task_file = potential_file
                break

        if not task_file:
            return None

        # Get file path
        file_path = os.path.join(execution_dir, task_file)

        # Read the task content if it's done or failed
        content = ""
        if task_file.endswith(('.done', '.failed')):
            with open(file_path, 'r') as f:
                content = f.read()

        # Get file size
        size = os.path.getsize(file_path)

        return {
            'content': content,
            'size': size
        }
    except Exception as e:
        print(f"Error getting task result: {str(e)}")
        return None

@app.route('/workflow/<workflow_name>/execution/<scan_id>/<path:task_name>/download')
def download_task_result(workflow_name, scan_id, task_name):
    try:
        # Get task result
        task_result = get_task_result(workflow_name, scan_id, task_name)
        if not task_result:
            return "Task result not found", 404

        # Create a response with the content
        response = make_response(task_result['content'])
        
        # Set headers for file download
        response.headers['Content-Type'] = 'text/plain'
        response.headers['Content-Disposition'] = f'attachment; filename={task_name.replace(":", "_")}_result.txt'
        
        return response
    except Exception as e:
        print(f"Error in download_task_result: {str(e)}")
        return f"Error downloading task result: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True,host='0.0.0.0',port=5001)