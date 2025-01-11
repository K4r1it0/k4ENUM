// static/js/workflow-editor.js

class WorkflowEditor {
    constructor(workflowName, viewOnly = false) {
        this.nodes = new vis.DataSet([]);
        this.edges = new vis.DataSet([]);
        this.network = null;
        this.workflowName = workflowName;
        this.viewOnly = viewOnly;
        // Predefined color palette that matches our dark theme
        this.colorPalette = [
            { background: '#1a1f2b', border: 'rgba(59, 130, 246, 0.5)' },  // Blue
            { background: '#1a1a24', border: 'rgba(168, 85, 247, 0.5)' },  // Purple
            { background: '#1a1f1a', border: 'rgba(16, 185, 129, 0.5)' },  // Green
            { background: '#1f1c1a', border: 'rgba(249, 115, 22, 0.5)' },  // Orange
            { background: '#1f1a1a', border: 'rgba(239, 68, 68, 0.5)' },   // Red
            { background: '#1a1f1f', border: 'rgba(6, 182, 212, 0.5)' },   // Cyan
            { background: '#1f1f1a', border: 'rgba(234, 179, 8, 0.5)' },   // Yellow
            { background: '#1f1a1f', border: 'rgba(236, 72, 153, 0.5)' }   // Pink
        ];
        this.moduleColorMap = new Map(); // Store module-color assignments
        this.colorIndex = 0; // Track next color to assign
        this.currentWorkflow = {
            config: {
                workflow: {
                    name: '',  // Initialize empty
                    description: '',  // Initialize empty
                    arguments: {},  // Initialize empty arguments object
                    modules: []
                }
            }
        };
        this.originalYaml = null;
        
        // Initialize the network first
        this.init().then(() => {
            // Set workflow name if provided
            if (workflowName && workflowName !== "None") {
                this.currentWorkflow.config.workflow.name = workflowName;
                this.updateWorkflowTitle(workflowName);
            } else if (!viewOnly) {
                // Show new workflow modal for new workflows in edit mode
                this.showNewWorkflowModal();
            }
        });
    }

    updateWorkflowTitle(name) {
        const titleElement = document.getElementById('workflow-title');
        if (titleElement) {
            // Capitalize each word in the workflow name
            const capitalizedName = name.split('_')
                .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                .join(' ');
            titleElement.textContent = capitalizedName;
            document.title = `k4ENUM - ${capitalizedName}`;

            // Add click event to edit workflow data
            titleElement.style.cursor = 'pointer';
            titleElement.onclick = () => this.showEditWorkflowModal();
        }
    }

    async init() {
        const container = document.getElementById('vis-viewer');
        const data = {
            nodes: this.nodes,
            edges: this.edges
        };

        // Get options from the global configuration
        const options = JSON.parse(JSON.stringify(window.visViewerControls.defaultOptions));
        
        // Override interaction settings for editor
        options.interaction.dragNodes = !this.viewOnly;
        options.interaction.selectable = !this.viewOnly;
        
        // Disable hover and selection color changes
        options.nodes = {
            ...options.nodes,
                    hover: {
                enabled: false
            },
            chosen: false
        };

        this.network = new vis.Network(container, data, options);
        
        // Disable physics after initial layout
        this.network.once('stabilizationIterationsDone', () => {
            this.network.setOptions({ physics: false });
        });

        this.setupEventListeners();
    }

    setupEventListeners() {
        if (this.viewOnly) return;

        this.network.on('select', (selection) => {
            const deleteBtn = document.querySelector('button[onclick="deleteSelected()"]');
            const addEdgeBtn = document.querySelector('button[data-action="link"]');
            
            if (selection.nodes.length > 0 || selection.edges.length > 0) {
                if (deleteBtn) deleteBtn.disabled = false;
            } else {
                if (deleteBtn) deleteBtn.disabled = true;
            }

            if (selection.nodes.length === 1) {
                if (addEdgeBtn) addEdgeBtn.disabled = false;
            } else {
                if (addEdgeBtn) addEdgeBtn.disabled = true;
            }
        });

        // Handle double click on nodes to edit
        this.network.on('doubleClick', (params) => {
            if (params.nodes.length === 1) {
                const nodeId = params.nodes[0];
                const [moduleName, taskName] = nodeId.split(':');
                
                // Find the task configuration
                const moduleConfig = this.currentWorkflow.config.workflow.modules.find(m => m.name === moduleName);
                if (!moduleConfig) return;
                
                const taskConfig = moduleConfig.tasks.find(t => Object.keys(t)[0] === taskName);
                if (!taskConfig) return;
                
                const task = taskConfig[taskName];

                // Show task properties modal
                const modal = new bootstrap.Modal(document.getElementById('taskPropertiesModal'));
                const saveButton = document.getElementById('saveTaskProperties');
                const moduleInput = document.getElementById('taskModule');
                const nameInput = document.getElementById('taskName');
                const commandInput = document.getElementById('taskCommand');
                const argumentsList = document.getElementById('moduleArgumentsList');

                // Set values
                moduleInput.value = moduleName;
                nameInput.value = taskName;
                commandInput.value = task.command || '';
                argumentsList.innerHTML = '';

                // Add existing arguments
                if (task.args) {
                    Object.entries(task.args).forEach(([key, value]) => {
                        const row = document.createElement('div');
                        row.className = 'argument-row';
                        row.innerHTML = `
                            <input type="text" class="form-control" placeholder="Key" value="${key}">
                            <input type="text" class="form-control" placeholder="Value" value="${value}">
                            <button type="button" class="btn-remove" onclick="this.parentElement.remove()">
                                <i class="bi bi-x-lg"></i>
                            </button>
                        `;
                        argumentsList.appendChild(row);
                    });
                }

                const saveHandler = () => {
                    const newModuleName = moduleInput.value.trim();
                    const newTaskName = nameInput.value.trim();
                    const newCommand = commandInput.value.trim();
                    
                    if (!newModuleName || !newTaskName || !newCommand) {
                        alert('Please fill in all required fields');
                        return;
                    }

                    // Get arguments if any
                    const args = this.getArgumentsFromForm('moduleArgumentsList');

                    // If the task name or module has changed, we need to update the node ID
                    const newTaskId = `${newModuleName}:${newTaskName}`;
                    const taskChanged = newTaskId !== nodeId;

                    if (taskChanged) {
                        // Update edges to point to the new node ID
                        const connectedEdges = this.network.getConnectedEdges(nodeId);
                        const edgesToUpdate = [];
                        
                        connectedEdges.forEach(edgeId => {
                            const edge = this.edges.get(edgeId);
                            if (edge.to === nodeId) {
                                edgesToUpdate.push({
                                    id: edgeId,
                                    from: edge.from,
                                    to: newTaskId
                                });
                            }
                        });

                        // Remove old node and add new one
                        this.nodes.remove(nodeId);
                        
                        // Get or assign module colors for the new module
                        if (!this.moduleColorMap.has(newModuleName)) {
                            this.moduleColorMap.set(newModuleName, this.colorPalette[this.colorIndex % this.colorPalette.length]);
                            this.colorIndex++;
                        }
                        const colors = this.moduleColorMap.get(newModuleName);

                        // Add new node
                        this.nodes.add({
                            id: newTaskId,
                            label: newTaskName.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                            color: colors
                        });

                        // Update edges
                        edgesToUpdate.forEach(edge => {
                            this.edges.update(edge);
                        });

                        // Remove old task from configuration
                        const oldModuleIndex = this.currentWorkflow.config.workflow.modules.findIndex(m => m.name === moduleName);
                        if (oldModuleIndex !== -1) {
                            const oldTasks = this.currentWorkflow.config.workflow.modules[oldModuleIndex].tasks;
                            const oldTaskIndex = oldTasks.findIndex(t => Object.keys(t)[0] === taskName);
                            if (oldTaskIndex !== -1) {
                                oldTasks.splice(oldTaskIndex, 1);
                            }
                            // Remove module if it's empty
                            if (oldTasks.length === 0) {
                                this.currentWorkflow.config.workflow.modules.splice(oldModuleIndex, 1);
                            }
                        }
                    }

                    // Update or create module in workflow configuration
                    let moduleIndex = this.currentWorkflow.config.workflow.modules.findIndex(m => m.name === newModuleName);
                    if (moduleIndex === -1) {
                        this.currentWorkflow.config.workflow.modules.push({
                            name: newModuleName,
                    tasks: []
                });
                        moduleIndex = this.currentWorkflow.config.workflow.modules.length - 1;
                    }

                    // Create new task configuration
                    const newTaskConfig = {
                        [newTaskName]: {
                            command: newCommand
                        }
                    };

                    if (Object.keys(args).length > 0) {
                        newTaskConfig[newTaskName].args = args;
                    }

                    // If task name changed, add as new task, otherwise update existing
                    if (taskChanged) {
                        this.currentWorkflow.config.workflow.modules[moduleIndex].tasks.push(newTaskConfig);
                        } else {
                        const taskIndex = this.currentWorkflow.config.workflow.modules[moduleIndex].tasks.findIndex(t => Object.keys(t)[0] === taskName);
                        if (taskIndex !== -1) {
                            this.currentWorkflow.config.workflow.modules[moduleIndex].tasks[taskIndex] = newTaskConfig;
                        }
                    }

                    // Update YAML view
                    this.updateYamlView();

                    // Clean up
                    modal.hide();
                    saveButton.removeEventListener('click', saveHandler);
                };

                saveButton.addEventListener('click', saveHandler);
                modal.show();
            }
        });

        // Add event listener for the Link button
        const linkButton = document.querySelector('button[data-action="link"]');
        if (linkButton) {
            console.log('Found link button, adding event listener');
            linkButton.onclick = (event) => {
                event.preventDefault();
                this.addEdge();
            };
                        } else {
            console.error('Link button not found');
        }
    }

    addNode() {
        // Check if we have a workflow name first
        if (!this.currentWorkflow.config.workflow.name) {
            this.showNewWorkflowModal();
            return;
        }

        const modal = new bootstrap.Modal(document.getElementById('taskPropertiesModal'));
        const saveButton = document.getElementById('saveTaskProperties');
        const moduleInput = document.getElementById('taskModule');
        const nameInput = document.getElementById('taskName');
        const commandInput = document.getElementById('taskCommand');
        const argumentsList = document.getElementById('moduleArgumentsList');
        
        // Clear previous values
        moduleInput.value = '';
        nameInput.value = '';
        commandInput.value = '';
        argumentsList.innerHTML = '';

        const saveHandler = () => {
            const moduleName = moduleInput.value.trim();
            const taskName = nameInput.value.trim();
            const command = commandInput.value.trim();
            
            if (!moduleName || !taskName || !command) {
                alert('Please fill in all required fields');
                return;
            }

            const taskId = `${moduleName}:${taskName}`;

            // Check for duplicate task
            const existingModule = this.currentWorkflow.config.workflow.modules.find(m => m.name === moduleName);
            if (existingModule && existingModule.tasks.some(t => Object.keys(t)[0] === taskName)) {
                alert('A task with this name already exists in this module. Please choose a different name.');
                return;
            }

            // Also check in visualization for duplicate task ID
            if (this.nodes.get(taskId)) {
                alert('A task with this name already exists in this module. Please choose a different name.');
                return;
            }

            // Get arguments if any
            const args = this.getArgumentsFromForm('moduleArgumentsList');

            // Get or assign module colors
            if (!this.moduleColorMap.has(moduleName)) {
                this.moduleColorMap.set(moduleName, this.colorPalette[this.colorIndex % this.colorPalette.length]);
                this.colorIndex++;
            }
            const colors = this.moduleColorMap.get(moduleName);

            try {
                // Add node to visualization
                this.nodes.add({
                    id: taskId,
                    label: taskName.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                    color: colors
                });

                // Find or create module in workflow configuration
                let moduleIndex = this.currentWorkflow.config.workflow.modules.findIndex(m => m.name === moduleName);
                if (moduleIndex === -1) {
                    this.currentWorkflow.config.workflow.modules.push({
                        name: moduleName,
                        tasks: []
                    });
                    moduleIndex = this.currentWorkflow.config.workflow.modules.length - 1;
                }

                // Add task to module
                const taskConfig = {
                    [taskName]: {
                        command: command
                    }
                };

                if (Object.keys(args).length > 0) {
                    taskConfig[taskName].args = args;
                }

                this.currentWorkflow.config.workflow.modules[moduleIndex].tasks.push(taskConfig);

                // Update YAML view
                this.updateYamlView();

                // Clean up
                modal.hide();
                saveButton.removeEventListener('click', saveHandler);

                // Force network update and fit view
                if (this.network) {
                    this.network.setData({
                        nodes: this.nodes,
                        edges: this.edges
                    });
                    setTimeout(() => {
                        this.network.fit();
                    }, 100);
                }
            } catch (error) {
                console.error('Error adding task:', error);
                alert('Error adding task: ' + error.message);
                
                // Clean up any partial additions
                try {
                    this.nodes.remove(taskId);
                } catch (e) {
                    console.error('Error cleaning up node:', e);
                }
            }
        };

        saveButton.addEventListener('click', saveHandler);
        modal.show();
    }

    addEdge() {
        console.log('addEdge method called');

        const handleEdgeAdd = (data, callback) => {
            console.log('addEdge event triggered', data);
            if (data.from && data.to) {
                console.log('Valid from and to nodes:', data.from, data.to);
                const fromId = data.from;
                const toId = data.to;

                // Prevent duplicate edges
                if (this.edges.get().some(e => e.from === fromId && e.to === toId)) {
                    console.log('Duplicate edge detected');
                    callback(null);
                    return;
                }

                // Add edge to visualization
                const edgeOptions = window.visViewerControls.defaultOptions.edges;
                try {
                    const edge = {
                        from: fromId,
                        to: toId,
                        ...edgeOptions
                    };
                    
                    // Update workflow configuration
                    const [toModule, toTask] = toId.split(':');
                    console.log('Updating task dependencies:', toModule, toTask);
                    
                    const moduleIndex = this.currentWorkflow.config.workflow.modules.findIndex(m => m.name === toModule);
                    if (moduleIndex === -1) {
                        console.error('Module not found:', toModule);
                        callback(null);
                        return;
                    }

                    const taskIndex = this.currentWorkflow.config.workflow.modules[moduleIndex].tasks.findIndex(t => Object.keys(t)[0] === toTask);
                    if (taskIndex === -1) {
                        console.error('Task not found:', toTask);
                        callback(null);
                        return;
                    }

                    // Get the current task configuration
                    const taskObj = this.currentWorkflow.config.workflow.modules[moduleIndex].tasks[taskIndex];
                    const taskName = Object.keys(taskObj)[0];
                    const task = { ...taskObj[taskName] };
                    console.log('Current task configuration:', task);

                    // Initialize requires array if it doesn't exist
                    if (!task.requires) {
                        task.requires = [];
                    }

                    // Add the fromId as the dependency if not already present
                    if (!task.requires.includes(fromId)) {
                        task.requires.push(fromId);
                        console.log('Updated requires array:', task.requires);
                        
                        // Update the task in the workflow configuration
                        this.currentWorkflow.config.workflow.modules[moduleIndex].tasks[taskIndex] = {
                            [taskName]: {
                                command: task.command,
                                requires: task.requires,
                                ...(task.args && { args: task.args })
                            }
                        };

                        console.log('Task configuration updated, calling updateYamlView');
                        // Force immediate YAML update
                        this.updateYamlView();
                    }

                    // Confirm the edge creation
                    callback(edge);
                } catch (error) {
                    console.error('Error adding edge:', error);
                    callback(null);
                }
            } else {
                console.log('Invalid edge data - missing from or to:', data);
                callback(null);
            }
        };

        // Set manipulation options without showing the toolbar
        this.network.setOptions({
            manipulation: {
                enabled: false,
                addEdge: handleEdgeAdd
            }
        });
        
        // Enable edge creation mode
        this.network.addEdgeMode();
        console.log('Edge mode enabled');
    }

    deleteSelected() {
        const selection = this.network.getSelection();
        
        // Remove selected nodes and their associated edges from visualization
        this.nodes.remove(selection.nodes);
        this.edges.remove(selection.edges);

        // Update workflow configuration
        selection.nodes.forEach(nodeId => {
            const [module, task] = nodeId.split(':');
            
            const moduleIndex = this.currentWorkflow.config.workflow.modules.findIndex(m => m.name === module);
            if (moduleIndex === -1) return;

            const moduleConfig = this.currentWorkflow.config.workflow.modules[moduleIndex];
            const taskIndex = moduleConfig.tasks.findIndex(t => Object.keys(t)[0] === task);
            if (taskIndex === -1) return;

            moduleConfig.tasks.splice(taskIndex, 1);

            // Remove module if it has no tasks
            if (moduleConfig.tasks.length === 0) {
                this.currentWorkflow.config.workflow.modules.splice(moduleIndex, 1);
                this.moduleColorMap.delete(module);
            }

            // Remove dependencies to this task
            this.currentWorkflow.config.workflow.modules.forEach(m => {
                m.tasks.forEach(t => {
                    const taskName = Object.keys(t)[0];
                    const taskConfig = t[taskName];
                    if (!taskConfig.requires) return;

                    if (typeof taskConfig.requires === 'string') {
                        if (taskConfig.requires === task || taskConfig.requires === nodeId) {
                            delete taskConfig.requires;
                }
            } else {
                        taskConfig.requires = taskConfig.requires.filter(r => r !== task && r !== nodeId);
                        if (taskConfig.requires.length === 0) {
                            delete taskConfig.requires;
                        }
                    }
                });
            });
        });

        this.updateYamlView();
    }

    zoomIn() {
        if (this.network) {
            const scale = this.network.getScale();
            this.network.moveTo({ scale: scale * 1.2 });
        }
    }

    zoomOut() {
        if (this.network) {
            const scale = this.network.getScale();
            this.network.moveTo({ scale: scale / 1.2 });
        }
    }

    zoomFit() {
        if (this.network) {
            this.network.fit();
        }
    }

    generateYaml() {
        // Create an ordered config object
        const orderedConfig = {
            workflow: {
                name: this.currentWorkflow.config.workflow.name || ''
            }
        };

        // Add description if it exists
        if (this.currentWorkflow.config.workflow.description) {
            orderedConfig.workflow.description = this.currentWorkflow.config.workflow.description;
        }

        // Add arguments if they exist
        if (this.currentWorkflow.config.workflow.arguments && Object.keys(this.currentWorkflow.config.workflow.arguments).length > 0) {
            orderedConfig.workflow.arguments = this.currentWorkflow.config.workflow.arguments;
        }

        // Add modules if they exist
        if (this.currentWorkflow.config.workflow.modules) {
            orderedConfig.workflow.modules = this.currentWorkflow.config.workflow.modules;
        }

        // Convert to YAML with proper formatting
        return jsyaml.dump(orderedConfig, {
            indent: 2,
            lineWidth: -1,
            noRefs: true,
            sortKeys: false,
            quotingType: '"',
            forceQuotes: true
        });
    }

    updateYamlView() {
        const yamlPreview = document.querySelector('.yaml-content code');
        if (!yamlPreview) {
            console.error('YAML preview element not found');
            return;
        }

        try {
            // Always generate fresh YAML when updating the view
            const yaml = this.generateYaml();

            // Create a new code element to ensure clean highlighting
            const newCode = document.createElement('code');
            newCode.className = 'language-yaml hljs';
            newCode.textContent = yaml;

            // Replace the old code element with the new one
            const pre = yamlPreview.parentElement;
            pre.innerHTML = '';
            pre.appendChild(newCode);
            
            // Apply syntax highlighting
            hljs.highlightElement(newCode);

            // Dispatch an event to notify that YAML has been updated
            const event = new CustomEvent('yamlUpdated', { detail: yaml });
            document.dispatchEvent(event);
        } catch (error) {
            console.error('Error updating YAML view:', error);
        }
    }

    async saveWorkflow() {
        try {
            // Check if we have a workflow name
            if (!this.currentWorkflow.config.workflow.name) {
                const name = prompt('Please enter a workflow name:');
                if (!name) {
                    throw new Error('Workflow name is required');
                }
                this.currentWorkflow.config.workflow.name = name;
                this.updateWorkflowTitle(name);
            }

            // Generate YAML with ordered properties
            const yaml = this.generateYaml();

            let url, method;
            if (this.workflowName) {
                // Existing workflow - use PUT
                url = `/api/workflow/${this.workflowName}`;
                method = 'PUT';
        } else {
                // New workflow - use POST
                url = '/api/workflow';
                method = 'POST';
            }

            const response = await fetch(url, {
                method: method,
                    headers: {
                        'Content-Type': 'application/json'
                    },
                        body: JSON.stringify({
                    name: this.currentWorkflow.config.workflow.name,
                    yaml: yaml
                        })
                    });

            if (!response.ok) throw new Error('Failed to save workflow');

            // Update the original YAML and workflow name
                const data = await response.json();
            this.originalYaml = yaml;
            if (!this.workflowName) {
                this.workflowName = this.currentWorkflow.config.workflow.name;
                // Redirect to the workflow editor page for the new workflow
                window.location.href = `/workflow/${this.workflowName}/edit`;
            }
            this.updateYamlView();
            
            // Show success message
            alert('Workflow saved successfully');
            } catch (error) {
            console.error('Error saving workflow:', error);
            alert('Failed to save workflow: ' + error.message);
        }
    }

    async runWorkflow() {
        try {
            // Get the current workflow configuration
            const config = this.currentWorkflow.config;
            
            // Check if workflow has arguments
            const hasArguments = config?.workflow?.args || [];
            
            if (hasArguments.length > 0) {
                // Clear previous arguments
                const form = document.getElementById('argumentsForm');
                form.innerHTML = '';
                
                // Add form fields for each argument
                hasArguments.forEach(arg => {
                    const argName = Object.keys(arg)[0];
                    const div = document.createElement('div');
                    div.className = 'mb-3';
                    div.innerHTML = `
                        <label for="arg-${argName}" class="form-label">${argName}</label>
                        <input type="text" class="form-control" id="arg-${argName}" 
                               name="${argName}" placeholder="Enter ${argName}" required>
                    `;
                    form.appendChild(div);
                });
                
                // Show the modal
                const modal = new bootstrap.Modal(document.getElementById('argumentsModal'));
                modal.show();
                
                // Handle run button click
                document.getElementById('runWithArgsBtn').onclick = () => {
                    const formData = new FormData(form);
                    const args = {};
                    for (let [key, value] of formData.entries()) {
                        args[key] = value;
                    }
                    this.startWorkflow(args);
                    modal.hide();
                };
            } else {
                // No arguments needed, run directly
                this.startWorkflow({});
            }
        } catch (e) {
            console.error('Error running workflow:', e);
            alert('Error running workflow configuration');
        }
    }

    async startWorkflow(args) {
        try {
            const response = await fetch(`/api/workflow/${this.workflowName}/run`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ args: args })
            });
            
            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }
            
            // Redirect to execution view
            window.location.href = `/workflow/${this.workflowName}/execution/${data.scan_id}`;
        } catch (error) {
            console.error('Error running workflow:', error);
            alert('Error running workflow: ' + error.message);
        }
    }

    getArgumentsFromForm(listId) {
        const args = {};
        const rows = document.querySelectorAll(`#${listId} .argument-row`);
        
        rows.forEach(row => {
            const key = row.querySelector('input[placeholder="Key"]').value.trim();
            const value = row.querySelector('input[placeholder="Value"]').value.trim();
            if (key && value) {
                args[key] = value;
            }
        });

        return args;
    }

    addArgumentField(listId) {
        const list = document.getElementById(listId);
        const row = document.createElement('div');
        row.className = 'argument-row';
        row.innerHTML = `
            <input type="text" class="form-control" placeholder="Key">
            <input type="text" class="form-control" placeholder="Value">
            <button type="button" class="btn-remove" onclick="this.parentElement.remove()">
                <i class="bi bi-x-lg"></i>
                            </button>
        `;
        list.appendChild(row);
    }

    showNewWorkflowModal() {
        const modal = new bootstrap.Modal(document.getElementById('newWorkflowModal'));
        const createButton = document.getElementById('createWorkflow');
        const nameInput = document.getElementById('workflowName');
        const descriptionInput = document.getElementById('workflowDescription');
        const argumentsList = document.getElementById('workflowArgumentsList');
        const modalTitle = document.getElementById('newWorkflowModalLabel');

        // Reset modal title and button text for new workflow
        if (modalTitle) {
            modalTitle.textContent = 'New Workflow';
        }
        if (createButton) {
            createButton.textContent = 'Create';
        }

        // Clear previous values
        nameInput.value = '';
        descriptionInput.value = '';
        argumentsList.innerHTML = '';

        const createHandler = () => {
            const name = nameInput.value.trim();
            const description = descriptionInput.value.trim();
            
            if (!name) {
                alert('Please provide a workflow name');
                return;
            }

            // Get arguments if any
            const args = this.getArgumentsFromForm('workflowArgumentsList');

            // Update workflow configuration
            this.currentWorkflow.config.workflow.name = name;
            if (description) {
                this.currentWorkflow.config.workflow.description = description;
            }
            if (Object.keys(args).length > 0) {
                this.currentWorkflow.config.workflow.args = args;
            }

            // Update UI
            this.updateWorkflowTitle(name);

            // Clean up
            modal.hide();
            createButton.removeEventListener('click', createHandler);
            
            // Update YAML view
            this.updateYamlView();
        };

        createButton.addEventListener('click', createHandler);
        modal.show();
    }

    showEditWorkflowModal() {
        const modal = new bootstrap.Modal(document.getElementById('newWorkflowModal'));
        const createButton = document.getElementById('createWorkflow');
        const nameInput = document.getElementById('workflowName');
        const descriptionInput = document.getElementById('workflowDescription');
        const argumentsList = document.getElementById('workflowArgumentsList');
        const modalTitle = document.getElementById('newWorkflowModalLabel');

        // Update modal title for edit mode
        if (modalTitle) {
            modalTitle.textContent = 'Edit Workflow';
        }
        if (createButton) {
            createButton.textContent = 'Save Changes';
        }

        // Fill in existing values
        nameInput.value = this.currentWorkflow.config.workflow.name || '';
        descriptionInput.value = this.currentWorkflow.config.workflow.description || '';
        argumentsList.innerHTML = '';

        // Fill in existing arguments
        const args = this.currentWorkflow.config.workflow.args || {};
        Object.entries(args).forEach(([key, value]) => {
            const row = document.createElement('div');
            row.className = 'argument-row';
            row.innerHTML = `
                <input type="text" class="form-control" placeholder="Key" value="${key}">
                <input type="text" class="form-control" placeholder="Value" value="${value}">
                <button type="button" class="btn-remove" onclick="this.parentElement.remove()">
                    <i class="bi bi-x-lg"></i>
                </button>
            `;
            argumentsList.appendChild(row);
        });

        const saveHandler = () => {
            const name = nameInput.value.trim();
            const description = descriptionInput.value.trim();
            
            if (!name) {
                alert('Please provide a workflow name');
                return;
            }

            // Get arguments if any
            const args = this.getArgumentsFromForm('workflowArgumentsList');

            // Update workflow configuration
            this.currentWorkflow.config.workflow.name = name;
            if (description) {
                this.currentWorkflow.config.workflow.description = description;
            } else {
                delete this.currentWorkflow.config.workflow.description;
            }
            if (Object.keys(args).length > 0) {
                this.currentWorkflow.config.workflow.args = args;
            } else {
                delete this.currentWorkflow.config.workflow.args;
            }

            // Update UI and YAML
            this.updateWorkflowTitle(name);
            // Force regenerate YAML by clearing originalYaml
            this.originalYaml = null;
            this.updateYamlView();

            // Clean up
            modal.hide();
            createButton.removeEventListener('click', saveHandler);

            // Reset modal title and button text
            if (modalTitle) {
                modalTitle.textContent = 'New Workflow';
            }
            if (createButton) {
                createButton.textContent = 'Create';
            }
        };

        createButton.addEventListener('click', saveHandler);
        modal.show();
    }

    async loadWorkflow(name) {
        try {
            const response = await fetch(`/api/workflow/${name}`);
            if (!response.ok) throw new Error('Failed to load workflow');

                const data = await response.json();
            this.currentWorkflow = { config: data.config };  // Wrap the config in the expected structure
            this.originalYaml = data.yaml;
            
            // Update YAML view
            this.updateYamlView();
            
        // Clear existing nodes and edges
        this.nodes.clear();
        this.edges.clear();
        
            // Create nodes and edges from workflow config
            if (data.config.workflow && data.config.workflow.modules) {
                // Create nodes
                data.config.workflow.modules.forEach(module => {
                    if (!module.tasks) return;
                    
                    // Get or assign module colors
                    if (!this.moduleColorMap.has(module.name)) {
                        this.moduleColorMap.set(module.name, this.colorPalette[this.colorIndex % this.colorPalette.length]);
                        this.colorIndex++;
                    }
                    const colors = this.moduleColorMap.get(module.name);
                    
                    module.tasks.forEach(taskObj => {
                        const taskName = Object.keys(taskObj)[0];
                        const taskId = `${module.name}:${taskName}`;
                        
                        this.nodes.add({
                            id: taskId,
                            label: taskName.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                            color: colors
                        });
                        
                        // Create edges from dependencies
                        const task = taskObj[taskName];
                        if (task.requires) {
                            const requires = Array.isArray(task.requires) ? task.requires : [task.requires];
                            requires.forEach(req => {
                                const fromId = req.includes(':') ? req : `${module.name}:${req}`;
                                const edgeOptions = window.visViewerControls.defaultOptions.edges;
                                this.edges.add({
                                    from: fromId,
                                    to: taskId,
                                    ...edgeOptions
                                });
                                    });
                                }
                            });
                });
            }
            
            // Initialize network if not already initialized
            if (!this.network) {
                await this.init();
            }
            
            // Update the title
            this.updateWorkflowTitle(name);
            
            // Fit the view
        setTimeout(() => {
            if (this.network) {
                this.network.fit();
            }
        }, 100);
            
        } catch (error) {
            console.error('Error loading workflow:', error);
            alert('Failed to load workflow: ' + error.message);
        }
    }
}

// Editor-specific options
const editorOptions = {
    yaml: { /* YAML editor settings */ },
    validation: { /* validation rules */ },
    ui: { /* editor UI settings */ }
};