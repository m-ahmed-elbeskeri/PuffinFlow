"""FlowForge project generator with enhanced dependency and import handling."""

import os
import yaml
import shutil
import sys
import re
import ast
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Set

try:
    from packages.codegen.code_generator import generate_python, validate_flow
except ImportError:
    # For standalone usage
    sys.path.append(str(Path(__file__).parent))
    from packages.codegen.code_generator import generate_python, validate_flow

def generate_project(flow_file: Union[str, Path], output_dir: str = "generated_project", 
                    project_name: Optional[str] = None, registry=None) -> Path:
    """
    Generate a deployable Python project from a flow definition file with comprehensive dependency handling.
    
    Args:
        flow_file: Path to the flow YAML file
        output_dir: Base directory for output (default: "generated_project")
        project_name: Custom project name (default: derive from flow ID)
        registry: Optional Registry instance for validation
        
    Returns:
        Path to the generated project directory
        
    Raises:
        ValueError: If flow file is invalid or project generation fails
    """
    # Ensure flow_file is a Path object
    flow_file = Path(flow_file)
    
    # Read and parse flow file
    try:
        with open(flow_file, 'r') as f:
            flow = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"Failed to read or parse flow file: {str(e)}")
    
    # Validate flow structure
    if not isinstance(flow, dict):
        raise ValueError("Flow definition must be a dictionary")
    
    # Validate flow content if registry is provided
    if registry:
        issues = validate_flow(flow, registry)
        errors = [msg for msg in issues if not msg.startswith("WARNING:")]
        warnings = [msg for msg in issues if msg.startswith("WARNING:")]

        if errors:
            error_msg = "Flow validation failed:\n" + "\n".join(f"- {e}" for e in errors)
            raise ValueError(error_msg)

        # Show warnings
        for w in warnings:
            print(w)
    
    # Determine project name
    project_name = project_name or flow.get('id') or flow.get('name') or 'flowforge_project'
    package_name = re.sub(r'[^a-zA-Z0-9_]', '_', project_name.lower())
    
    # Create project directory structure
    project_dir = Path(output_dir) / package_name
    workflow_dir = project_dir / "workflow"
    integrations_dir = project_dir / "integrations"
    
    # Create directories
    for directory in [project_dir, workflow_dir, integrations_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    
    # Create standard project files
    create_init_file(project_dir)
    create_init_file(workflow_dir)
    create_init_file(integrations_dir)
    
    # Enhanced requirements collection and generation
    all_requirements = collect_all_requirements(flow, registry)
    create_requirements_file(project_dir, all_requirements)
    
    create_setup_file(project_dir, package_name)
    create_run_script(project_dir, package_name)
    
    # Generate flow implementation files
    create_flow_code(workflow_dir, flow, registry)
    create_run_py(workflow_dir)
    
    # Enhanced integration copying with dependency resolution
    create_integrations_from_registry(integrations_dir, flow, registry)
    
    # Generate .env file if needed
    env_content = generate_env_file_content(flow, registry)
    if env_content.strip():
        (project_dir / ".env").write_text(env_content)
    
    # Validate the generated project
    validation_issues = validate_project_dependencies(project_dir, flow, registry)
    if validation_issues:
        print("Warning: Project validation found issues:")
        for issue in validation_issues:
            print(f"  - {issue}")
    
    return project_dir

def collect_all_requirements(flow: Dict[str, Any], registry=None) -> Set[str]:
    """Collect all requirements from flow and its integrations."""
    requirements = {
        "pyyaml>=6.0",
        "requests>=2.25.0"
    }
    
    # Detect integrations used
    used_integrations = set()
    for step in flow.get("steps", []):
        if "action" in step and "." in step["action"]:
            integration, _ = step["action"].split(".", 1)
            if integration not in ("variables", "basic", "control"):
                used_integrations.add(integration)
    
    # Add integration-specific requirements
    for integration in used_integrations:
        integration_reqs = get_integration_requirements(integration, registry)
        requirements.update(integration_reqs)
    
    # Detect special features
    if detect_env_vars_usage(flow):
        requirements.add("python-dotenv>=0.15.0")
    
    if detect_http_usage(flow):
        requirements.add("requests>=2.25.0")  # Ensure requests is included
    
    if detect_async_usage(flow):
        requirements.add("asyncio")  # Usually built-in, but explicit
    
    return requirements

def get_integration_requirements(integration_name: str, registry=None) -> Set[str]:
    """Get requirements for a specific integration."""
    requirements = set()
    
    # Try multiple sources for requirements
    sources = [
        get_from_registry_manifest(integration_name, registry),
        get_from_integration_handler(integration_name),
        get_from_filesystem(integration_name),
    ]
    
    for source_reqs in sources:
        if source_reqs:
            requirements.update(source_reqs)
            break  # Use first successful source
    
    return requirements

def get_from_registry_manifest(integration_name: str, registry) -> Set[str]:
    """Get requirements from registry manifest."""
    if not registry or not hasattr(registry, 'integrations'):
        return set()
    
    integration_data = registry.integrations.get(integration_name, {})
    manifest = integration_data.get('manifest', {})
    return set(manifest.get('requirements', []))

def get_from_integration_handler(integration_name: str) -> Set[str]:
    """Get requirements from integration handler."""
    try:
        from packages.codegen.integration_handler import IntegrationHandler
        handler = IntegrationHandler()
        integration_info = handler.get_integration_info(integration_name)
        if integration_info:
            return set(integration_info.get('requirements', []))
    except Exception:
        pass
    return set()

def get_from_filesystem(integration_name: str) -> Set[str]:
    """Get requirements from filesystem (requirements.txt in integration dir)."""
    possible_paths = [
        Path("integrations") / integration_name / "requirements.txt",
        Path("../integrations") / integration_name / "requirements.txt",
        Path("../../integrations") / integration_name / "requirements.txt",
    ]
    
    for req_path in possible_paths:
        if req_path.exists():
            try:
                with open(req_path, 'r') as f:
                    reqs = set()
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            reqs.add(line)
                    return reqs
            except Exception:
                continue
    
    return set()

def detect_env_vars_usage(flow: Dict[str, Any]) -> bool:
    """Detect if flow uses environment variables."""
    for step in flow.get("steps", []):
        if step.get("action") == "variables.get_env":
            return True
        
        # Check for template strings with env variables
        for input_name, input_value in step.get("inputs", {}).items():
            if isinstance(input_value, str):
                if "{{env." in input_value or "{env." in input_value:
                    return True
    
    return False

def detect_http_usage(flow: Dict[str, Any]) -> bool:
    """Detect if flow uses HTTP operations."""
    for step in flow.get("steps", []):
        action = step.get("action", "")
        if action.startswith(("http.", "https.", "api.", "rest.", "graphql.")):
            return True
    return False

def detect_async_usage(flow: Dict[str, Any]) -> bool:
    """Detect if flow uses async operations."""
    for step in flow.get("steps", []):
        action = step.get("action", "")
        if "async" in action or "await" in action:
            return True
    return False

def create_requirements_file(project_dir: Path, requirements: Set[str]) -> None:
    """Create enhanced requirements.txt with proper formatting and comments."""
    sorted_requirements = sorted(requirements)
    
    content = [
        "# FlowForge Generated Project Requirements",
        "# Core dependencies",
        "",
    ]
    
    # Separate core and integration requirements
    core_reqs = []
    integration_reqs = []
    
    for req in sorted_requirements:
        if any(core in req.lower() for core in ['pyyaml', 'requests', 'python-dotenv']):
            core_reqs.append(req)
        else:
            integration_reqs.append(req)
    
    # Add core requirements
    content.extend(core_reqs)
    
    # Add integration requirements if any
    if integration_reqs:
        content.extend(["", "# Integration dependencies", ""])
        content.extend(integration_reqs)
    
    content.append("")  # Final newline
    
    (project_dir / "requirements.txt").write_text("\n".join(content))

def create_integrations_from_registry(
    integrations_dir: Path, 
    flow: Dict[str, Any], 
    registry=None
) -> None:
    """Enhanced integration copying with dependency resolution."""
    
    required_integrations = collect_required_integrations(flow)
    copied_integrations = set()
    
    for integration_name in required_integrations:
        copy_integration_with_dependencies(
            integration_name, 
            integrations_dir, 
            registry, 
            copied_integrations,
            required_integrations       
        )

def copy_integration_with_dependencies(
    integration_name: str,
    target_dir: Path,
    registry,
    copied_set: Set[str],
    required_integrations: Dict[str, Dict[str, Set[str]]]
) -> None:
    if integration_name in copied_set:
        return

    success = copy_single_integration(integration_name, target_dir, registry, required_integrations)
    if success:
        copied_set.add(integration_name)

        dependencies = find_integration_dependencies(integration_name, registry)
        for dep in dependencies:
            copy_integration_with_dependencies(dep, target_dir, registry, copied_set, required_integrations)


def copy_single_integration(
    integration_name: str,
    target_dir: Path,
    registry,
    required_integrations: Dict[str, Dict[str, Set[str]]]
) -> bool:
    """
    Copy only the required modules (.py files) from an integration.
    
    Uses: `registry.plugins[integration]['path']` or filesystem fallback.
    Will only copy modules declared as used in the manifest.
    """
    target_integration_dir = target_dir / integration_name
    target_integration_dir.mkdir(exist_ok=True)
    create_init_file(target_integration_dir)

    used_modules = required_integrations.get(integration_name, {}).keys()

    # Try plugin path first
    source_dir = None
    if registry and hasattr(registry, 'plugins'):
        plugin_info = registry.plugins.get(integration_name)
        if plugin_info and 'path' in plugin_info:
            candidate = Path(plugin_info['path'])
            if candidate.exists():
                source_dir = candidate

    # Fallback to filesystem
    if source_dir is None:
        possible_paths = [
            Path("integrations") / integration_name,
            Path("../integrations") / integration_name,
            Path("../../integrations") / integration_name,
        ]
        for path in possible_paths:
            if path.exists() and path.is_dir():
                source_dir = path
                break

    if source_dir is None:
        print(f"[WARN] Integration source not found: {integration_name}")
        return False

    success = False
    for module in used_modules:
        py_file = source_dir / f"{module}.py"
        if py_file.exists():
            shutil.copy2(py_file, target_integration_dir / py_file.name)
            success = True
        else:
            print(f"[WARN] Expected module '{module}.py' not found in '{integration_name}'")

    if success:
        print(f"Copied modules from integration '{integration_name}' -> {', '.join(used_modules)}")
    return success


def copy_from_registry_plugins(
    integration_name: str,
    target_dir: Path,
    registry
) -> bool:
    """Copy integration from registry plugins."""
    if not registry or not hasattr(registry, 'plugins'):
        return False
    
    plugin_info = registry.plugins.get(integration_name)
    if not plugin_info:
        return False
    
    source_path = plugin_info.get('path')
    if not source_path or not Path(source_path).exists():
        return False
    
    try:
        # Copy all Python files from source
        source_dir = Path(source_path)
        for py_file in source_dir.glob("*.py"):
            if py_file.name != "__init__.py":  # We create our own
                shutil.copy2(py_file, target_dir / py_file.name)
        
        print(f"Copied integration '{integration_name}' from registry plugins")
        return True
    except Exception as e:
        print(f"Error copying from registry plugins for '{integration_name}': {e}")
        return False

def copy_from_filesystem(integration_name: str, target_dir: Path) -> bool:
    """Copy integration from filesystem."""
    possible_sources = [
        Path("integrations") / integration_name,
        Path("../integrations") / integration_name,
        Path("../../integrations") / integration_name,
    ]
    
    for source_dir in possible_sources:
        if source_dir.exists() and source_dir.is_dir():
            try:
                for py_file in source_dir.glob("*.py"):
                    if py_file.name != "__init__.py":
                        shutil.copy2(py_file, target_dir / py_file.name)
                
                print(f"Copied integration '{integration_name}' from filesystem")
                return True
            except Exception as e:
                print(f"Error copying from filesystem for '{integration_name}': {e}")
                continue
    
    return False

def create_from_manifest(integration_name: str, target_dir: Path, registry) -> bool:
    """Create integration from manifest definition."""
    if not registry or not hasattr(registry, 'integrations'):
        return False
    
    integration_data = registry.integrations.get(integration_name)
    if not integration_data:
        return False
    
    manifest = integration_data.get('manifest', {})
    actions = manifest.get('actions', {})
    
    if not actions:
        return False
    
    try:
        # Group actions by module
        modules = {}
        for action_name, action_def in actions.items():
            implementation = action_def.get('implementation', '')
            if '.' in implementation:
                module_name, _ = implementation.split('.', 1)
            else:
                module_name = action_name
            
            if module_name not in modules:
                modules[module_name] = []
            modules[module_name].append((action_name, action_def))
        
        # Create module files
        for module_name, module_actions in modules.items():
            create_module_implementation(
                target_dir / f"{module_name}.py",
                integration_name,
                module_name,
                module_actions
            )
        
        print(f"Created integration '{integration_name}' from manifest")
        return True
    except Exception as e:
        print(f"Error creating from manifest for '{integration_name}': {e}")
        return False

def create_stub_implementation(integration_name: str, target_dir: Path) -> bool:
    """Create a stub implementation as last resort."""
    try:
        stub_content = f'''"""Stub implementation for {integration_name} integration."""

def default_action(**kwargs):
    """Default action for {integration_name} integration."""
    print(f"Executing {integration_name} action with args: {{kwargs}}")
    return {{"status": "success", "result": None}}

# Add any integration-specific functions here
'''
        
        (target_dir / f"{integration_name}.py").write_text(stub_content)
        print(f"Created stub implementation for '{integration_name}'")
        return True
    except Exception as e:
        print(f"Error creating stub for '{integration_name}': {e}")
        return False

def create_module_implementation(
    module_file: Path,
    integration_name: str,
    module_name: str,
    actions: List[tuple]
) -> None:
    """Create implementation for a module with its actions."""
    lines = [
        f'"""Implementation of {integration_name}.{module_name} functions."""',
        '',
        '# Add any necessary imports here',
        'import os',
        'import json',
        ''
    ]
    
    # Add integration-specific imports
    if integration_name in ['http', 'https', 'api']:
        lines.append('import requests')
        lines.append('')
    elif integration_name in ['email', 'smtp']:
        lines.append('import smtplib')
        lines.append('from email.mime.text import MIMEText')
        lines.append('')
    elif integration_name in ['database', 'db', 'sqlite']:
        lines.append('import sqlite3')
        lines.append('')
    
    # Create functions for each action
    for action_name, action_def in actions:
        lines.extend(create_action_function(action_name, action_def))
        lines.append('')
    
    module_file.write_text('\n'.join(lines))

def create_action_function(action_name: str, action_def: Dict[str, Any]) -> List[str]:
    """Create a function implementation for an action."""
    description = action_def.get('description', f'Execute {action_name}')
    inputs = action_def.get('inputs', {})
    outputs = action_def.get('outputs', {})
    
    # Generate function signature
    params = []
    for input_name, input_def in inputs.items():
        if isinstance(input_def, dict):
            if input_def.get('required', False):
                params.append(input_name)
            else:
                default = input_def.get('default', 'None')
                if isinstance(default, str) and not default.startswith(('None', 'True', 'False')):
                    default = f'"{default}"'
                params.append(f'{input_name}={default}')
        else:
            params.append(f'{input_name}=None')
    
    if not params:
        params = ['**kwargs']
    
    lines = [
        f'def {action_name}({", ".join(params)}):',
        f'    """',
        f'    {description}',
        f'    """'
    ]
    
    # Generate function body based on action type
    if action_name in ['get', 'fetch', 'download']:
        lines.extend([
            '    # HTTP GET implementation',
            '    try:',
            '        import requests',
            '        response = requests.get(url, timeout=30)',
            '        return {"status": response.status_code, "body": response.text}',
            '    except Exception as e:',
            '        return {"error": str(e)}'
        ])
    elif action_name in ['post', 'send', 'submit']:
        lines.extend([
            '    # HTTP POST implementation',
            '    try:',
            '        import requests',
            '        response = requests.post(url, json=data, timeout=30)',
            '        return {"status": response.status_code, "body": response.text}',
            '    except Exception as e:',
            '        return {"error": str(e)}'
        ])
    elif action_name in ['read', 'load']:
        lines.extend([
            '    # File read implementation',
            '    try:',
            '        with open(path, "r") as f:',
            '            content = f.read()',
            '        return {"content": content}',
            '    except Exception as e:',
            '        return {"error": str(e)}'
        ])
    elif action_name in ['write', 'save']:
        lines.extend([
            '    # File write implementation',
            '    try:',
            '        with open(path, "w") as f:',
            '            f.write(content)',
            '        return {"success": True}',
            '    except Exception as e:',
            '        return {"error": str(e)}'
        ])
    else:
        # Generic implementation
        if outputs:
            output_dict = ', '.join([f'"{name}": None' for name in outputs.keys()])
            lines.append(f'    return {{{output_dict}}}')
        else:
            lines.append('    return {"status": "success"}')
    
    return lines

def find_integration_dependencies(integration_name: str, registry) -> Set[str]:
    """Find dependencies of an integration."""
    dependencies = set()
    
    # Check manifest for dependencies
    if registry and hasattr(registry, 'integrations'):
        integration_data = registry.integrations.get(integration_name, {})
        manifest = integration_data.get('manifest', {})
        deps = manifest.get('dependencies', [])
        dependencies.update(deps)
    
    # Check Python files for imports from other integrations
    source_dir = find_source_integration_dir(integration_name, registry)
    if source_dir:
        python_deps = scan_python_files_for_integrations(source_dir)
        dependencies.update(python_deps)
    
    return dependencies

def find_source_integration_dir(integration_name: str, registry) -> Optional[Path]:
    """Find the source directory for an integration."""
    # Try registry first
    if registry and hasattr(registry, 'plugins'):
        plugin_info = registry.plugins.get(integration_name)
        if plugin_info and 'path' in plugin_info:
            path = Path(plugin_info['path'])
            if path.exists():
                return path
    
    # Try filesystem
    possible_paths = [
        Path("integrations") / integration_name,
        Path("../integrations") / integration_name,
        Path("../../integrations") / integration_name,
    ]
    
    for path in possible_paths:
        if path.exists() and path.is_dir():
            return path
    
    return None

def scan_python_files_for_integrations(source_dir: Path) -> Set[str]:
    """Scan Python files for imports from other integrations."""
    dependencies = set()
    
    for py_file in source_dir.glob("*.py"):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse imports
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith('integrations.'):
                        # Extract integration name
                        parts = node.module.split('.')
                        if len(parts) >= 2:
                            dependencies.add(parts[1])
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith('integrations.'):
                            parts = alias.name.split('.')
                            if len(parts) >= 2:
                                dependencies.add(parts[1])
        except Exception:
            # Skip files that can't be parsed
            continue
    
    return dependencies

def collect_required_integrations(flow: Dict[str, Any]) -> Dict[str, Dict[str, Set[str]]]:
    """Collect integrations, modules and actions required by the flow."""
    required = {}
    
    # Set of integrations to exclude (handled natively)
    excluded_integrations = {'variables'}
    
    for step in flow.get("steps", []):
        if "action" in step:
            action = step["action"]
            if '.' in action:
                integration, action_name = action.split(".", 1)
                
                # Skip excluded integrations
                if integration in excluded_integrations:
                    continue
                
                # Initialize integration entry if needed
                if integration not in required:
                    required[integration] = {}
                
                # Determine module name
                module_name = action_name
                if integration == "control":
                    module_name = "control"
                elif '_' in action_name:
                    module_name = action_name.split('_')[0]
                
                # Add to required modules
                if module_name not in required[integration]:
                    required[integration][module_name] = set()
                
                required[integration][module_name].add(action_name)
    
    return required

def generate_env_file_content(flow: Dict[str, Any], registry=None) -> str:
    """Generate .env file content for a flow."""
    env_vars = set()
    
    # Collect environment variables from flow
    for step in flow.get("steps", []):
        if step.get("action") == "variables.get_env":
            env_name = step.get("inputs", {}).get("name")
            if env_name and isinstance(env_name, str):
                env_vars.add(env_name)
        
        # Check for template strings with env variables
        for input_name, input_value in step.get("inputs", {}).items():
            if isinstance(input_value, str):
                matches = re.findall(r'\{\{(?:\s*env\.)([a-zA-Z0-9_]+)(?:\s*)\}\}', input_value)
                env_vars.update(matches)
                
                matches = re.findall(r'\{(?:\s*env\.)([a-zA-Z0-9_]+)(?:\s*)\}', input_value)
                env_vars.update(matches)
    
    if not env_vars:
        return ""
    
    flow_id = flow.get("id", "flow")
    lines = [
        f"# Environment variables for flow: {flow_id}",
        "# Fill in the values below for environment variables used in this flow",
        ""
    ]
    
    for var_name in sorted(env_vars):
        lines.append(f"{var_name}=")
    
    return "\n".join(lines) + "\n"

def validate_project_dependencies(
    project_dir: Path,
    flow: Dict[str, Any],
    registry=None
) -> List[str]:
    """Validate that all required dependencies are available."""
    issues = []
    
    # Check requirements.txt exists and has content
    req_file = project_dir / "requirements.txt"
    if not req_file.exists():
        issues.append("requirements.txt not found")
    else:
        requirements = set()
        try:
            with open(req_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Extract package name (before >= or ==)
                        pkg_name = line.split('>=')[0].split('==')[0].split('[')[0]
                        requirements.add(pkg_name.lower())
        except Exception as e:
            issues.append(f"Error reading requirements.txt: {e}")
            return issues
        
        # Check for missing core requirements
        core_deps = ['pyyaml', 'requests']
        for dep in core_deps:
            if not any(dep in req for req in requirements):
                issues.append(f"Missing core dependency: {dep}")
    
    # Check integration files exist
    required_integrations = collect_required_integrations(flow)
    integrations_dir = project_dir / "integrations"
    
    for integration in required_integrations:
        integration_dir = integrations_dir / integration
        if not integration_dir.exists():
            issues.append(f"Missing integration directory: {integration}")
        else:
            # Check for __init__.py
            if not (integration_dir / "__init__.py").exists():
                issues.append(f"Missing __init__.py in integration: {integration}")
            
            # Check for at least one Python file
            py_files = list(integration_dir.glob("*.py"))
            if len(py_files) <= 1:  # Only __init__.py
                issues.append(f"No implementation files in integration: {integration}")
    
    # Check flow.py exists
    flow_file = project_dir / "workflow" / "flow.py"
    if not flow_file.exists():
        issues.append("Missing workflow/flow.py")
    
    # Check run.py exists
    run_file = project_dir / "workflow" / "run.py"
    if not run_file.exists():
        issues.append("Missing workflow/run.py")
    
    return issues

def create_init_file(directory: Path) -> None:
    """Create an __init__.py file in the specified directory."""
    (directory / "__init__.py").write_text('"""FlowForge generated package."""\n')

def create_setup_file(project_dir: Path, package_name: str) -> None:
    """Create a setup.py file in the project directory."""
    requirements_list = []
    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        try:
            with open(req_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        requirements_list.append(f'        "{line}",')
        except Exception:
            # Fallback requirements
            requirements_list = [
                '        "pyyaml>=6.0",',
                '        "requests>=2.25.0",'
            ]
    
    setup_content = f"""from setuptools import setup, find_packages

setup(
    name="{package_name}",
    version="0.1.0",
    description="FlowForge generated project for {package_name}",
    author="FlowForge",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
{chr(10).join(requirements_list)}
    ],
    entry_points={{
        'console_scripts': [
            '{package_name}=workflow.run:main',
        ],
    }},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
"""
    
    (project_dir / "setup.py").write_text(setup_content)

def create_run_script(project_dir: Path, package_name: str) -> None:
    """Create a run.sh script for easy execution."""
    run_script_content = f"""#!/bin/bash
# FlowForge Project Runner

set -e  # Exit on error

echo "Setting up FlowForge project: {package_name}"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "Error: Python is not installed or not in PATH"
        exit 1
    else
        PYTHON_CMD="python"
    fi
else
    PYTHON_CMD="python3"
fi

echo "Using Python: $PYTHON_CMD"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment"
        echo "Make sure python3-venv is installed (apt-get install python3-venv on Ubuntu/Debian)"
        exit 1
    fi
fi

# Activate virtual environment
echo "Activating virtual environment..."
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -e .
if [ $? -ne 0 ]; then
    echo "Failed to install dependencies"
    exit 1
fi

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Note: .env file found. Environment variables will be loaded by the flow."
fi

# Run the flow
echo "Running the flow..."
$PYTHON_CMD -m workflow.run

echo "Flow execution completed!"
"""
    
    run_path = project_dir / "run.sh"
    run_path.write_text(run_script_content)
    try:
        os.chmod(run_path, 0o755)
    except Exception:
        pass  # Windows doesn't support chmod

def create_flow_code(workflow_dir: Path, flow: Dict[str, Any], registry=None) -> None:
    """Generate and write the Python code implementing the flow."""
    flow_code = generate_python(flow, registry, use_native_control=True)
    flow_file = workflow_dir / "flow.py"
    flow_file.write_text(flow_code)

def create_run_py(workflow_dir: Path) -> None:
    """Create a run.py module for executing the flow."""
    run_content = '''"""Flow execution script."""

from workflow.flow import run_flow
import json
import os
import sys

def main():
    """Execute the flow and return the result."""
    # Load .env file if it exists
    if os.path.exists(".env"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print("Loaded environment variables from .env file.")
        except ImportError:
            print("Warning: python-dotenv not installed. Environment variables from .env file will not be loaded.")
    elif os.path.exists("../.env"):
        try:
            from dotenv import load_dotenv
            load_dotenv("../.env")
            print("Loaded environment variables from ../.env file.")
        except ImportError:
            print("Warning: python-dotenv not installed. Environment variables from .env file will not be loaded.")
    
    try:
        print("Starting flow execution...")
        result = run_flow()
        
        print("\\nFlow execution completed successfully!")
        print("=" * 50)
        
        # Try to make result JSON-serializable for display
        try:
            result_str = json.dumps(result, indent=2, default=str)
            print("Flow Result:")
            print(result_str)
        except (TypeError, ValueError):
            print(f"Flow Result (not JSON serializable): {result}")
            
        return result
        
    except KeyboardInterrupt:
        print("\\nFlow execution interrupted by user.")
        return None
        
    except Exception as e:
        print(f"\\nError executing flow: {type(e).__name__}: {str(e)}")
        
        # Print traceback in debug mode
        if os.environ.get("FLOWFORGE_DEBUG", "").lower() in ("1", "true", "yes"):
            import traceback
            print("\\nFull traceback:")
            traceback.print_exc()
        else:
            print("\\nFor detailed error information, set FLOWFORGE_DEBUG=1")
            
        return None

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result is not None else 1)
'''
    (workflow_dir / "run.py").write_text(run_content)