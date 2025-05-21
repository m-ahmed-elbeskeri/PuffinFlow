"""FlowForge project generator using centralized code generation logic."""

import os
import yaml
import shutil
import sys
from pathlib import Path
import re
from typing import Dict, Any, List, Optional, Union, Set

try:
    from packages.codegen.code_generator import generate_python,  validate_flow
except ImportError:
    # For standalone usage
    sys.path.append(str(Path(__file__).parent))
    from packages.codegen.code_generator import generate_python, validate_flow

def generate_project(flow_file: Union[str, Path], output_dir: str = "generated_project", 
                    project_name: Optional[str] = None, registry=None) -> Path:
    """
    Generate a deployable Python project from a flow definition file.
    
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
        errors = validate_flow(flow, registry)
        if errors:
            error_msg = "Flow validation failed:\n" + "\n".join(f"- {error}" for error in errors)
            raise ValueError(error_msg)
    
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
    create_requirements_file(project_dir)
    create_setup_file(project_dir, package_name)
    create_run_script(project_dir, package_name)
    
    # Generate flow implementation files
    create_flow_code(workflow_dir, flow, registry)
    create_run_py(workflow_dir)
    
    # Copy or create integration files based on registry definitions
    create_integrations_from_registry(integrations_dir, flow, registry)
    
    return project_dir

def create_init_file(directory: Path) -> None:
    """Create an __init__.py file in the specified directory."""
    (directory / "__init__.py").write_text('"""FlowForge generated package."""\n')

def create_requirements_file(project_dir: Path, flow: Dict[str, Any] = None, registry = None) -> None:
    """
    Create a requirements.txt file in the project directory including dependencies 
    from all integrations used in the flow.
    
    Args:
        project_dir: Directory to write requirements.txt
        flow: Flow definition to scan for used integrations
        registry: Registry instance to locate integration directories
    """
    # Base requirements
    requirements = {
        "pyyaml>=6.0",
        "requests>=2.25.0"
    }
    
    # Only process integrations if flow and registry are provided
    if flow and registry:
        # Find all integrations used in the flow
        used_integrations = set()
        for step in flow.get("steps", []):
            if "action" in step and "." in step["action"]:
                integration, _ = step["action"].split(".", 1)
                used_integrations.add(integration)
        
        # Find integrations directories
        integrations_dir = None
        
        # Try to find integrations directory from registry
        if hasattr(registry, 'integrations_dir'):
            integrations_dir = Path(registry.integrations_dir)
        else:
            # Try to locate it relative to registry's module
            module_path = Path(sys.modules.get(registry.__module__, __name__).__file__).parent
            candidate_dirs = [
                module_path.parent / 'integrations',
                module_path / 'integrations',
                Path.cwd() / 'integrations'
            ]
            
            for candidate in candidate_dirs:
                if candidate.exists() and candidate.is_dir():
                    integrations_dir = candidate
                    break
        
        # Scan each used integration for requirements.txt
        if integrations_dir:
            for integration in used_integrations:
                integration_dir = integrations_dir / integration
                req_file = integration_dir / "requirements.txt"
                
                if req_file.exists():
                    try:
                        # Read and parse requirements from file
                        with open(req_file, 'r') as f:
                            for line in f:
                                line = line.strip()
                                # Skip comments and empty lines
                                if line and not line.startswith('#'):
                                    requirements.add(line)
                        print(f"Added requirements from {integration} integration")
                    except Exception as e:
                        print(f"Error reading requirements from {integration}: {str(e)}")
    
    # Sort requirements alphabetically
    sorted_requirements = sorted(requirements)
    
    # Write to file
    (project_dir / "requirements.txt").write_text("\n".join(sorted_requirements) + "\n")


def create_setup_file(project_dir: Path, package_name: str) -> None:
    """
    Create a setup.py file in the project directory with all required dependencies.
    
    Args:
        project_dir: Path to the project directory
        package_name: Name of the package
    """
    # Read requirements from requirements.txt
    requirements = []
    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        try:
            with open(req_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        requirements.append(f"        \"{line}\",")
        except Exception as e:
            print(f"Warning: Error reading requirements.txt: {str(e)}")
            # Fallback to basic requirements
            requirements = [
                "        \"pyyaml>=6.0\",",
                "        \"requests>=2.25.0\","
            ]
    else:
        # Fallback to basic requirements
        requirements = [
            "        \"pyyaml>=6.0\",",
            "        \"requests>=2.25.0\","
        ]
    
    # Generate setup.py content
    setup_content = f"""from setuptools import setup, find_packages

setup(
    name="{package_name}",
    version="0.1.0",
    description="FlowForge generated project for {package_name}",
    author="FlowForge",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
{chr(10).join(requirements)}
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
    
    try:
        (project_dir / "setup.py").write_text(setup_content)
        print(f"Generated setup.py with {len(requirements)} dependencies")
    except Exception as e:
        print(f"Error writing setup.py: {str(e)}")
        # Try to create a minimal setup.py if the full one fails
        try:
            minimal_setup = f"""from setuptools import setup, find_packages

setup(
    name="{package_name}",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["pyyaml>=6.0", "requests>=2.25.0"],
    entry_points={{
        'console_scripts': [
            '{package_name}=workflow.run:main',
        ],
    }},
)
"""
            (project_dir / "setup.py").write_text(minimal_setup)
            print("Generated minimal setup.py due to error with full version")
        except Exception as e2:
            print(f"Failed to create even minimal setup.py: {str(e2)}")
            raise RuntimeError(f"Failed to generate project setup.py: {str(e)}")
        
def create_run_script(project_dir: Path, package_name: str) -> None:
    """Create a run.sh script for easy execution."""
    run_script_content = f"""#!/bin/bash
pip install -e .
python -m workflow.run
"""
    
    run_path = project_dir / "run.sh"
    run_path.write_text(run_script_content)
    os.chmod(run_path, 0o755)

def create_flow_code(workflow_dir: Path, flow: Dict[str, Any], registry=None) -> None:
    """Generate and write the Python code implementing the flow."""
    print(f"DEBUG: create_flow_code - workflow_dir: {workflow_dir.absolute()}")
    
    # Verify the workflow directory exists and is writable
    if not workflow_dir.exists():
        print(f"DEBUG: Creating workflow directory: {workflow_dir.absolute()}")
        workflow_dir.mkdir(parents=True, exist_ok=True)
    
    if not os.access(workflow_dir, os.W_OK):
        print(f"DEBUG: Warning - workflow directory is not writable: {workflow_dir.absolute()}")
    
    # Pass the workflow directory to generate_python so it can place .env file there
    flow_code = generate_python(flow, registry, use_native_control=True, output_dir=workflow_dir)
    
    # Write the flow.py file
    flow_file = workflow_dir / "flow.py"
    print(f"DEBUG: Writing flow code to: {flow_file.absolute()}")
    try:
        flow_file.write_text(flow_code)
        print(f"DEBUG: Successfully wrote flow code to: {flow_file.absolute()}")
    except Exception as e:
        print(f"DEBUG: Error writing flow code: {str(e)}")

def create_run_py(workflow_dir: Path) -> None:
    """Create a run.py module for executing the flow."""
    run_content = """\"\"\"Flow execution script.\"\"\"

from workflow.flow import run_flow
import json

def main():
    \"\"\"Execute the flow and return the result.\"\"\"
    try:
        result = run_flow()
        
        # Try to make result JSON-serializable for display
        try:
            result_str = json.dumps(result, indent=2)
            print(f"Flow completed successfully. Result:")
            print(result_str)
        except (TypeError, ValueError):
            print(f"Flow completed successfully. Result: {result}")
            
        return result
    except Exception as e:
        print(f"Error executing flow: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()
"""
    (workflow_dir / "run.py").write_text(run_content)

def create_integrations_from_registry(integrations_dir: Path, flow: Dict[str, Any], registry=None) -> None:
    """
    Copy integration files from the source or create implementation files based on registry plugin definitions.
    
    Args:
        integrations_dir: Output directory for integration files
        flow: Flow definition dictionary
        registry: Registry instance for finding integration definitions
    """
    if not registry:
        print("Warning: Registry not provided, cannot create integration files")
        return
    
    # Identify the source integrations directory
    source_integrations_dir = find_integrations_dir(registry)
    
    # Collect required integrations and actions from the flow
    required_integrations = collect_required_integrations(flow)
    
    # Process each required integration
    for integration_name, actions_by_module in required_integrations.items():
        # Create the integration directory
        target_integration_dir = integrations_dir / integration_name
        target_integration_dir.mkdir(exist_ok=True)
        create_init_file(target_integration_dir)
        
        # Get the integration manifest from the registry
        integration_manifest = None
        if integration_name in registry.integrations:
            integration_manifest = registry.integrations[integration_name]
        
        # Get plugin info if available
        plugin_info = registry.plugins.get(integration_name) if hasattr(registry, 'plugins') else None
        
        # Process each module in this integration
        for module_name, actions in actions_by_module.items():
            # First check if this module is part of a plugin and can be copied directly
            if source_integrations_dir:
                source_module_file = source_integrations_dir / integration_name / f"{module_name}.py"
                if source_module_file.exists():
                    shutil.copy2(source_module_file, target_integration_dir / f"{module_name}.py")
                    print(f"Copied {integration_name}.{module_name} from {source_module_file}")
                    continue
            
            # If we couldn't copy from source, create implementation based on registry
            if integration_manifest:
                create_implementation_from_manifest(
                    target_integration_dir, 
                    integration_name, 
                    module_name, 
                    actions, 
                    integration_manifest
                )
            else:
                # Fallback if no manifest is available
                create_basic_implementation(target_integration_dir, integration_name, module_name, actions)

def find_integrations_dir(registry) -> Optional[Path]:
    """Find the source integrations directory."""
    # Multiple approaches to find the integrations directory
    candidates = [
        # If registry tracks its integrations_dir
        getattr(registry, 'integrations_dir', None),
        
        # Relative to the module that defined the registry
        Path(sys.modules.get(registry.__module__, __name__).__file__).parent.parent / 'integrations',
        
        # Relative to the current script
        Path(__file__).resolve().parent.parent / 'integrations',
        
        # Relative to current working directory
        Path.cwd() / 'integrations',
        Path.cwd().parent / 'integrations'
    ]
    
    # Filter out None values and check existence
    for candidate in [c for c in candidates if c]:
        if isinstance(candidate, str):
            candidate = Path(candidate)
        if candidate.exists() and candidate.is_dir():
            return candidate
    
    print("Warning: Could not find source integrations directory")
    return None

def collect_required_integrations(flow: Dict[str, Any]) -> Dict[str, Dict[str, Set[str]]]:
    """
    Collect integrations, modules and actions required by the flow.
    Excludes variables integration that is handled natively.
    
    Returns:
        Dictionary mapping integration_name -> {module_name -> set(action_names)}
    """
    required = {}
    
    # Set of integrations to exclude (handled natively)
    excluded_integrations = {'variables'}
    
    # Native variable operations that should be excluded
    native_variable_ops = {
        'variables.get_local', 'variables.set_local', 
        'variables.get_env', 'variables.get', 'variables.set'
    }
    
    for step in flow.get("steps", []):
        if "action" in step:
            action = step["action"]
            if '.' in action:
                integration, action_name = action.split(".", 1)
                
                # Skip excluded integrations
                if integration in excluded_integrations:
                    continue
                
                # Skip native variable operations
                if action in native_variable_ops:
                    continue
                
                # Initialize integration entry if needed
                if integration not in required:
                    required[integration] = {}
                
                # For plugin implementations, default to using the action name as module name
                module_name = action_name
                
                # Special case handling
                if integration == "control":
                    module_name = "control"
                elif '_' in action_name:
                    module_name = action_name.split('_')[0]
                
                # Add to required modules
                if module_name not in required[integration]:
                    required[integration][module_name] = set()
                
                required[integration][module_name].add(action_name)
    
    return required

def create_implementation_from_manifest(
    target_dir: Path, 
    integration_name: str, 
    module_name: str, 
    actions: Set[str], 
    manifest: Dict[str, Any]
) -> None:
    """
    Create implementation files based on definitions in the manifest.
    
    Args:
        target_dir: Target directory for the module file
        integration_name: Name of the integration
        module_name: Name of the module to create
        actions: Set of actions to implement
        manifest: Integration manifest with action definitions
    """
    module_file = target_dir / f"{module_name}.py"
    
    # Special handling for control module
    if integration_name == "control" and module_name == "control":
        content = generate_control_implementation()
        module_file.write_text(content)
        print(f"Created implementation for {integration_name}.{module_name}")
        return
    
    # Get manifest actions
    manifest_actions = manifest.get("actions", {})
    
    # Generate module content
    lines = [f'"""Implementation of {integration_name}.{module_name} functions."""\n']
    
    # Create implementation for each action
    for action in sorted(actions):
        # Get action definition from manifest
        action_def = manifest_actions.get(action, {})
        description = action_def.get("description", f"Execute {action}")
        
        # Get inputs with proper parameter definitions
        inputs = action_def.get("inputs", {})
        outputs = action_def.get("outputs", {})
        
        # Build parameter list
        params = []
        default_params = []
        
        for input_name, input_def in inputs.items():
            # Handle both dictionary and string input definitions
            if isinstance(input_def, dict):
                required = input_def.get("required", False)
                
                if required:
                    params.append(input_name)
                else:
                    default_value = input_def.get("default", "None")
                    if isinstance(default_value, str) and not default_value.startswith(("'", '"')):
                        default_value = f'"{default_value}"'
                    default_params.append(f"{input_name}={default_value}")
            else:
                # Simple string input type
                default_params.append(f"{input_name}=None")
        
        # Combine required and optional parameters
        all_params = params + default_params
        
        # Add **kwargs if no parameters defined
        if not all_params:
            all_params = ["**kwargs"]
        
        # Create function definition
        lines.append(f"def {action}({', '.join(all_params)}):")
        lines.append(f'    """{description}"""')
        
        # Create implementation based on the action and outputs
        if outputs:
            # Create functional implementation for common operations
            if action == "add":
                lines.append("    result = 0")
                for param in params[:2]:  # Use up to first two parameters
                    lines.append(f"    result += {param}")
                output_name = next(iter(outputs.keys()))
                lines.append(f'    return {{"{output_name}": result}}\n')
            elif action == "multiply":
                lines.append("    result = 1")
                for param in params[:2]:  # Use up to first two parameters
                    lines.append(f"    result *= {param}")
                output_name = next(iter(outputs.keys()))
                lines.append(f'    return {{"{output_name}": result}}\n')
            elif action == "ask":
                lines.append("    question_text = question")
                lines.append("    print(f\"\\n{question_text}\")")
                lines.append("    answer = input(\"> \")")
                lines.append("    if type == \"number\":")
                lines.append("        try:")
                lines.append("            answer = float(answer)")
                lines.append("        except ValueError:")
                lines.append("            pass")
                lines.append('    return {"answer": answer}\n')
            elif action == "notify":
                lines.append("    print(f\"\\n{message}\")")
                lines.append('    return {"status": "displayed", "level": level}\n')
            else:
                # Create a functional generic implementation
                output_items = []
                for output_name, output_type in outputs.items():
                    if isinstance(output_type, str):
                        if output_type.lower() in ('number', 'int', 'float'):
                            output_items.append(f'"{output_name}": 0')
                        elif output_type.lower() in ('string', 'str', 'text'):
                            output_items.append(f'"{output_name}": ""')
                        elif output_type.lower() in ('boolean', 'bool'):
                            output_items.append(f'"{output_name}": False')
                        elif output_type.lower() in ('array', 'list'):
                            output_items.append(f'"{output_name}": []')
                        elif output_type.lower() in ('object', 'dict', 'map'):
                            output_items.append(f'"{output_name}": {{}}')
                        else:
                            output_items.append(f'"{output_name}": None')
                    else:
                        output_items.append(f'"{output_name}": None')
                
                output_dict = ", ".join(output_items)
                lines.append(f"    return {{{output_dict}}}\n")
        else:
            lines.append(f'    return {{"status": "success"}}\n')
    
    # Write the module file
    module_file.write_text("\n".join(lines))
    print(f"Created implementation for {integration_name}.{module_name}")

def create_basic_implementation(target_dir: Path, integration_name: str, module_name: str, actions: Set[str]) -> None:
    """
    Create a basic implementation when no manifest is available.
    
    Args:
        target_dir: Target directory for the module file
        integration_name: Name of the integration
        module_name: Name of the module to create
        actions: Set of actions to implement
    """
    module_file = target_dir / f"{module_name}.py"
    
    # Generate module content
    lines = [f'"""Implementation of {integration_name}.{module_name} functions."""\n']
    
    # Special handling for control module
    if integration_name == "control" and module_name == "control":
        content = generate_control_implementation()
        module_file.write_text(content)
        print(f"Created implementation for {integration_name}.{module_name}")
        return
    else:
        # Create a generic implementation for each action
        for action in sorted(actions):
            lines.append(f"def {action}(**kwargs):")
            lines.append(f'    """Execute {action} for the {integration_name} integration."""')
            
            # Try to infer the return value based on action name
            if action in ["add", "sum", "calculate"]:
                lines.append('    return {"sum": 0}\n')
            elif action in ["multiply", "product"]:
                lines.append('    return {"product": 0}\n')
            elif action in ["ask", "prompt", "input"]:
                lines.append('    return {"answer": "Sample response"}\n')
            elif action in ["notify", "alert", "message"]:
                lines.append('    return {"status": "displayed"}\n')
            else:
                lines.append('    return {"result": None}\n')
    
    # Write the module file
    module_file.write_text("\n".join(lines))
    print(f"Created basic implementation for {integration_name}.{module_name}")


