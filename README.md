# k4ENUM v2.0

Just another modular domain enumeration framework.

## Features

- Modular workflow-based architecture
- Parallel task execution with dependency management
- Real-time task status tracking
- Centralized or local Luigi scheduler support
- Multiple workflow execution support
- Automatic output organization
- Rich console output

## Usage

```bash
python3 scan.py -l                                    # List workflows
python3 scan.py -w passive -a domain=example.com      # Run workflow
python3 scan.py -w passive active -a domain=example.com  # Multiple workflows
python3 scan.py -w passive -c                         # Use central scheduler
```

## Workflow Structure

The framework uses YAML-based workflow configurations. Example structure:

```yaml
workflow:
  name: "passive"
  description: "Passive reconnaissance"
  modules:
    - name: "recon_module"
      tasks:
        - task_name:
            command: "command to execute"
            requires: ["dependency1", "dependency2"]
``` 