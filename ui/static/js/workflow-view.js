// static/js/workflow-view.js

class WorkflowViewer {
    constructor(workflowName, scanId) {
        this.workflowName = workflowName;
        this.scanId = scanId;
        this.nodes = new vis.DataSet([]);
        this.edges = new vis.DataSet([]);
        this.network = null;
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
        this.edgeColors = {
            normal: { color: 'rgba(255, 255, 255, 0.15)', highlight: 'rgba(255, 255, 255, 0.25)', hover: 'rgba(255, 255, 255, 0.25)' },
            active: { color: 'rgba(33, 150, 243, 0.6)', highlight: 'rgba(33, 150, 243, 0.8)', hover: 'rgba(33, 150, 243, 0.8)' }
        };
        this.lastTaskStatuses = new Map(); // Track last known status of each task
        this.updateInterval = null;
        this.executionExists = true;
        this.init();
    }

    init() {
        const container = document.getElementById('vis-viewer');
        
        // Get options from the global configuration
        const options = JSON.parse(JSON.stringify(window.visViewerControls.defaultOptions));
        
        // Override interaction settings for viewer
        options.interaction.dragNodes = false;
        options.interaction.selectable = false;

        const data = {
            nodes: this.nodes,
            edges: this.edges
        };

        this.network = new vis.Network(container, data, options);
        
        // Start periodic status updates only if we have a scan ID
        if (this.scanId) {
            this.startStatusUpdates();
        }
    }

    startStatusUpdates() {
        // Update status immediately
        this.updateTaskStatus();
        
        // Then update every 5 seconds if execution exists
        if (this.executionExists) {
            this.updateInterval = setInterval(() => {
                this.updateTaskStatus();
            }, 5000);
        }
    }

    stopStatusUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    async updateTaskStatus() {
        if (!this.executionExists) return;

        try {
            const response = await fetch(`/api/workflow/${this.workflowName}/execution/${this.scanId}/details`);
            if (!response.ok) {
                if (response.status === 404) {
                    console.log('Execution not found, stopping updates');
                    this.executionExists = false;
                    this.stopStatusUpdates();
                }
                return;
            }

            const data = await response.json();
            const tasks = data.tasks || [];
            let hasChanges = false;

            // Check if any task status has changed
            tasks.forEach(task => {
                if (!task || !task.name) return;  // Skip invalid tasks
                const lastStatus = this.lastTaskStatuses.get(task.name);
                if (lastStatus !== task.status) {
                    hasChanges = true;
                    this.lastTaskStatuses.set(task.name, task.status);
                }
            });

            // Only update if there are changes
            if (!hasChanges) {
                return;
            }

            // Reset all edges to normal state
            this.edges.forEach(edge => {
                this.edges.update({
                    ...edge,
                    color: this.edgeColors.normal,
                    dashes: false,
                    width: 2
                });
            });

            // Update node labels and edge colors based on status
            this.nodes.forEach(node => {
                if (!node || !node.id) return;  // Skip invalid nodes
                const taskId = node.id;
                const task = tasks.find(t => t && t.name === taskId);
                if (task) {
                    const status = task.status;
                    
                    // Update node label with formatted name
                    this.nodes.update({
                        id: taskId,
                        label: this.formatTaskName(taskId)
                    });

                    // Update edges for active or completed tasks
                    if (status === 'running' || status === 'done') {
                        // Update incoming edges to show progress
                        const incomingEdges = this.edges.get().filter(edge => edge.to === taskId);
                        incomingEdges.forEach(edge => {
                            this.edges.update({
                                ...edge,
                                color: this.edgeColors.active,
                                width: status === 'running' ? 3 : 2,
                                dashes: status === 'running' ? [2, 2] : false
                            });
                        });

                        // If task is done, update outgoing edges too
                        if (status === 'done') {
                            const outgoingEdges = this.edges.get().filter(edge => edge.from === taskId);
                            outgoingEdges.forEach(edge => {
                                this.edges.update({
                                    ...edge,
                                    color: this.edgeColors.active,
                                    width: 2,
                                    dashes: false
                                });
                            });
                        }
                    }
                }
            });

            // Update task table if it exists and has changes
            const taskTable = document.querySelector('.task-table tbody');
            if (taskTable) {
                // Sort tasks by status priority
                const statusPriority = {
                    'running': 0,
                    'pending': 1,
                    'done': 2,
                    'failed': 3
                };

                const sortedTasks = [...tasks].filter(task => task && task.name).sort((a, b) => {
                    return statusPriority[a.status] - statusPriority[b.status];
                });

                // Update only rows that have changed
                sortedTasks.forEach(task => {
                    if (!task.name) return;  // Skip tasks without names
                    const [moduleName, taskName] = task.name.split(':');
                    if (!moduleName || !taskName) return;  // Skip invalid task names

                    const existingRow = taskTable.querySelector(`tr[data-task-id="${task.name}"]`);
                    const newRowHtml = `
                        <td>
                            <div class="d-flex align-items-center">
                                <span class="status-circle status-${task.status}"></span>
                                <div class="task-info">
                                    <span class="module-name">${moduleName}</span>
                                    <span class="task-name">${this.formatTaskName(taskName)}</span>
                                </div>
                            </div>
                        </td>
                    `;

                    if (existingRow) {
                        if (existingRow.getAttribute('data-status') !== task.status) {
                            existingRow.setAttribute('data-status', task.status);
                            existingRow.innerHTML = newRowHtml;
                        }
                    } else {
                        const newRow = document.createElement('tr');
                        newRow.setAttribute('data-task-id', task.name);
                        newRow.setAttribute('data-status', task.status);
                        newRow.innerHTML = newRowHtml;
                        taskTable.appendChild(newRow);
                    }
                });

                // Re-apply current filter
                if (typeof window.filterTasks === 'function') {
                    window.filterTasks();
                }
            }

        } catch (error) {
            console.error('Error updating task status:', error);
        }
    }

    // Helper function to format task names
    formatTaskName(name) {
        if (!name) return '';
        const taskName = name.includes(':') ? name.split(':')[1] : name;
        return taskName
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
            .join(' ');
    }

    createVisualization(config) {
        if (!config || !config.workflow || !config.workflow.modules) {
            console.error('Invalid workflow configuration');
            return;
        }

        // Clear existing nodes and edges
        this.nodes.clear();
        this.edges.clear();

        const addedNodes = new Set();
        const edges = [];

        // Process each module
        config.workflow.modules.forEach(module => {
            if (!module.tasks) return;

            // Get module colors
            const moduleColors = this.getModuleColor(module.name);

            // Add nodes for each task
            module.tasks.forEach(taskObj => {
                const taskName = Object.keys(taskObj)[0];
                const taskConfig = taskObj[taskName];
                const nodeId = `${module.name}:${taskName}`;

                if (!addedNodes.has(nodeId)) {
                    this.nodes.add({
                        id: nodeId,
                        label: this.formatTaskName(taskName),
                        color: {
                            background: moduleColors.background,
                            border: moduleColors.border,
                            highlight: {
                                background: '#1e1e1e',
                                border: 'rgba(255, 255, 255, 0.3)'
                            },
                            hover: {
                                background: '#1e1e1e',
                                border: 'rgba(255, 255, 255, 0.3)'
                            }
                        }
                    });
                    addedNodes.add(nodeId);
                }

                // Process dependencies
                if (taskConfig.requires) {
                    const requires = Array.isArray(taskConfig.requires) 
                        ? taskConfig.requires 
                        : [taskConfig.requires];

                    requires.forEach(dep => {
                        const fromId = dep.includes(':') 
                            ? dep 
                            : `${module.name}:${dep}`;
                        edges.push({ from: fromId, to: nodeId });
                    });
                }
            });
        });

        // Add all edges after nodes are created
        edges.forEach(edge => {
            const edgeOptions = window.visViewerControls.defaultOptions.edges;
            this.edges.add({
                ...edge,
                ...edgeOptions
            });
        });

        // Organize the layout
        this.network.stabilize();
    }

    // Get color for a module, assigning a new one if needed
    getModuleColor(moduleName) {
        if (!this.moduleColorMap.has(moduleName)) {
            // Get next color from palette, cycling if we run out
            const color = this.colorPalette[this.colorIndex % this.colorPalette.length];
            this.moduleColorMap.set(moduleName, color);
            this.colorIndex++;
        }
        return this.moduleColorMap.get(moduleName);
    }

    // Helper method to generate consistent hash for strings
    hashString(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash);
    }

    zoomIn() {
        if (this.network) {
            const scale = this.network.getScale() * 1.2;
            this.network.moveTo({ scale: scale });
        }
    }

    zoomOut() {
        if (this.network) {
            const scale = this.network.getScale() / 1.2;
            this.network.moveTo({ scale: scale });
        }
    }

    zoomFit() {
        if (this.network) {
            this.network.fit();
        }
    }
} 