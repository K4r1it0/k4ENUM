I need to extend an existing Python framework called k4ENUM (a modular domain enumeration framework built on Luigi) to support distributed execution across multiple machines. The current system runs tasks locally using Luigi's scheduling, but I want to create a distributed version where multiple nodes can share workload.

The source code consists of:
1. scan.py - Main entry point with Framework class, command-line interface
2. loader.py - Handles loading workflow configurations via WorkflowLoader class
3. task_classes.py - Defines TaskExecution and ModuleTask classes (Luigi tasks)

The system currently:
- Uses Luigi for task scheduling and dependency management
- Executes shell commands via subprocess.run()
- Tracks task status with file extensions (.pending, .running, .done, .failed)
- Sets workers=len(all_tasks) for maximum parallelism

I need code for the following components:

1. CENTRAL SERVER SETUP:
- A script to set up the central Luigi scheduler (luigid)
- Configuration for shared storage (NFS or similar)
- A node management database/system to track connected nodes

2. NODE REGISTRATION SYSTEM:
- A Python script that takes IP, username, and private key path
- Automatically installs k4ENUM and dependencies on remote nodes
- Configures nodes to connect to the central scheduler
- Sets up shared storage access on the node
- Creates a systemd service for auto-starting workers

3. MODIFIED k4ENUM CODE:
- Updates to scan.py to support distributed execution
- Changes to path handling to use shared storage for task outputs
- Improved worker count strategy based on available resources
- Connection to central scheduler instead of local scheduler

4. MONITORING TOOLS:
- A script to monitor node health and task progress
- Dashboard or CLI to view distributed task execution
- Log aggregation from all nodes

Please provide code samples, installation steps, and usage examples for each component. The solution should be easy to deploy and scale to dozens of nodes.
