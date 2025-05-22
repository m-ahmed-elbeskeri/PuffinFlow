"""Code generation for FlowForge flows with improved IR-based implementation."""

import re
import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Set, Tuple

# Import the new IR system
from packages.codegen.ir import IRFlow
from packages.codegen.ir_builder import IRBuilder
from packages.codegen.python_printer import PythonPrinter
from packages.codegen.validator import FlowValidator, ValidationIssue
from packages.codegen.integration_handler import IntegrationHandler

# Global variables for caching and optimization
_ir_builder = None
_python_printer = None
_integration_handler = None
_validator = None

def _get_ir_builder(registry=None):
    """Get or create the IR builder instance."""
    global _ir_builder
    if _ir_builder is None:
        _ir_builder = IRBuilder(registry)
    return _ir_builder

def _get_python_printer(use_native_control=True, integration_handler=None): # Added integration_handler
    """Get or create the Python printer instance."""
    global _python_printer
    # Re-initialize if use_native_control changed OR if integration_handler is different or newly provided
    if _python_printer is None or \
       _python_printer.use_native_control != use_native_control or \
       _python_printer.integration_handler != integration_handler:
        _python_printer = PythonPrinter(
            use_native_control=use_native_control,
            integration_handler=integration_handler # Pass it here
        )
    return _python_printer

def _get_integration_handler():
    """Get or create the integration handler instance."""
    global _integration_handler
    if _integration_handler is None:
        # Ensure IntegrationHandler is imported if not already.
        # from packages.codegen.integration_handler import IntegrationHandler # Already imported at top
        integrations_dir = os.environ.get("FLOWFORGE_INTEGRATIONS_DIR", "./integrations")
        _integration_handler = IntegrationHandler(integrations_dir)
    return _integration_handler

def _get_validator(registry=None):
    """Get or create the validator instance."""
    global _validator
    if _validator is None:
        _validator = FlowValidator(registry)
        # If validator needs integration_handler for fallbacks, it should get it itself or be passed.
        # Current FlowValidator._get_fallback_ih() instantiates its own.
    return _validator

def validate_flow(flow: Dict[str, Any], registry=None) -> List[str]:
    """
    Validate a flow definition and return a list of validation errors.
    Uses the new IR-based validator internally.
    
    Args:
        flow: Flow definition dictionary
        registry: Optional Registry instance
        
    Returns:
        List of validation error messages
    """
    builder = _get_ir_builder(registry)
    validator = _get_validator(registry)
    
    # Convert to IR
    ir_flow = builder.build_flow(flow)
    
    # Validate
    issues = validator.validate_flow(ir_flow)
    
    # Convert issues to strings
    return [str(issue) for issue in issues]

def generate_mermaid(flow: Dict[str, Any]) -> str:
    """
    Generate a Mermaid diagram from a flow definition.
    This is a bridge function that uses the new IR-based system.
    
    Args:
        flow: Flow definition dictionary
        
    Returns:
        Mermaid diagram as string
    """
    from packages.codegen.python_printer import generate_mermaid as ir_generate_mermaid
    
    # Use the IR builder to convert the flow to IR
    builder = _get_ir_builder()
    ir_flow = builder.build_flow(flow)
    
    # Generate Mermaid diagram from IR
    return ir_generate_mermaid(ir_flow)

def generate_python(flow: Dict[str, Any], registry=None, use_native_control: bool = True) -> str:
    """
    Generate Python code from a flow definition using the new IR-based system.
    Maintains the original function signature for backward compatibility.
    
    Args:
        flow: Flow definition dictionary
        registry: Optional registry for action implementation lookup
        use_native_control: Whether to use native Python control structures
        
    Returns:
        Generated Python code as string
    """
    builder = _get_ir_builder(registry)
    ir_flow = builder.build_flow(flow)
    
    integration_h = _get_integration_handler() # Get the handler
    
    # Pass the handler to the printer factory
    printer = _get_python_printer(
        use_native_control=use_native_control,
        integration_handler=integration_h
    )
    
    return printer.print_flow(ir_flow)

def generate_typescript(flow: Dict[str, Any], output_type: str = "function", react_component: bool = False) -> str:
    """
    Generate TypeScript code from a flow definition.
    This is a new function that uses the IR-based system.
    
    Args:
        flow: Flow definition dictionary
        output_type: Type of output ("class", "function", or "react")
        react_component: Whether to generate a React component
        
    Returns:
        Generated TypeScript code as string
    """
    from packages.codegen.typescript_printer import TypeScriptPrinter
    
    builder = _get_ir_builder()
    ir_flow = builder.build_flow(flow)
    
    integration_h = _get_integration_handler()
    # Note: TypeScriptPrinter in this file structure does not seem to take integration_handler
    # in its constructor. If it needs it, its constructor and _get_typescript_printer (if created)
    # would need similar updates. However, the current TypeScriptPrinter provided in the prompt
    # does not use integration_handler. If the TypeScriptPrinter from the newer codegen.py is meant
    # to be used, that one *does* accept it. Assuming the one in this context.
    
    printer = TypeScriptPrinter(output_type=output_type, react_component=react_component)
    # If TypeScriptPrinter needs integration_handler, it would be:
    # printer = TypeScriptPrinter(output_type=output_type, react_component=react_component, integration_handler=integration_h)
    return printer.print_flow(ir_flow)

def generate_env_file(flow: Dict[str, Any], output_path: Optional[Path] = None) -> str:
    """
    Generate a .env file template for a flow.
    This is a new function that uses the IR-based system.
    
    Args:
        flow: Flow definition dictionary
        output_path: Optional path to write .env file
        
    Returns:
        Generated .env file content
    """
    builder = _get_ir_builder()
    ir_flow = builder.build_flow(flow)
    
    validator = _get_validator()
    validator.validate_flow(ir_flow) # This collects env_vars in validator.env_vars
    env_vars = validator.env_vars
    
    flow_id = flow.get("id", "flow")
    lines = [
        f"# Environment variables for flow: {flow_id}",
        "# Fill in the values below for environment variables used in this flow",
        ""
    ]
    
    for var_name in sorted(env_vars):
        lines.append(f"{var_name}=")
    
    content = "\n".join(lines)
    
    if output_path is not None:
        with open(output_path, "w") as f:
            f.write(content)
    
    return content

def generate_project(
    flow_file: Union[Path, str], 
    output_dir: str = "generated_project",
    project_name: Optional[str] = None, 
    registry=None
) -> Path:
    """
    Generate a deployable Python project from a flow definition file.
    Uses the new IR-based system while maintaining the original function signature.
    
    Args:
        flow_file: Path to the flow YAML file
        output_dir: Base directory for output
        project_name: Custom project name
        registry: Optional Registry instance
        
    Returns:
        Path to the generated project directory
    """
    # Parse flow file if it's a Path or string
    if isinstance(flow_file, (Path, str)):
        path = Path(flow_file) if isinstance(flow_file, str) else flow_file
        with open(path, 'r') as f:
            flow = yaml.safe_load(f)
    else:
        flow = flow_file  # Assume it's already a dict
    
    # Determine project name
    if project_name is None:
        project_name = flow.get('id') or flow.get('name') or 'flowforge_project'
    package_name = re.sub(r'[^a-zA-Z0-9_]', '_', project_name.lower())
    
    # Create project directory structure
    project_dir = Path(output_dir) / package_name
    workflow_dir = project_dir / "workflow"
    integrations_dir = project_dir / "integrations"
    
    # Create directories
    for directory in [project_dir, workflow_dir, integrations_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    
    # Create standard project files
    for dir_path in [project_dir, workflow_dir, integrations_dir]:
        (dir_path / "__init__.py").write_text('"""FlowForge generated package."""\n')
        
    # Generate requirements.txt
    _create_requirements_file(project_dir, flow, registry)
    
    # Generate setup.py
    _create_setup_file(project_dir, package_name)
    
    # Generate run.sh
    _create_run_script(project_dir, package_name)
    
    # Generate flow.py using the new IR-based system
    # generate_python now ensures printer gets integration_handler
    python_code = generate_python(flow, registry, use_native_control=True)
    (workflow_dir / "flow.py").write_text(python_code)
    
    # Generate run.py
    _create_run_py(workflow_dir)
    
    # Generate .env file if environment variables are detected by validator
    # (which is now more reliably done via IR)
    env_content = generate_env_file(flow) # Use the dedicated function
    if [line for line in env_content.splitlines() if "=" in line and not line.startswith("#")]: # Check if actual vars exist
        (project_dir / ".env").write_text(env_content)
    
    # Generate TypeScript files if requested (new feature!)
    if os.environ.get("FLOWFORGE_GENERATE_TYPESCRIPT", "0") == "1":
        ts_dir = project_dir / "typescript"
        ts_dir.mkdir(exist_ok=True)
        
        # Generate TypeScript function
        ts_code = generate_typescript(flow, output_type="function")
        (ts_dir / f"{package_name}.ts").write_text(ts_code)
        
        # Generate React component
        react_code = generate_typescript(flow, output_type="react", react_component=True)
        (ts_dir / f"{package_name.capitalize()}Component.tsx").write_text(react_code)
    
    return project_dir

def _create_requirements_file(project_dir: Path, flow: Dict[str, Any], registry=None) -> None:
    """Create a requirements.txt file for the project."""
    # Base requirements
    requirements = {
        "pyyaml>=6.0",
        "requests>=2.25.0"
    }
    
    # Add python-dotenv if env vars are used
    validator = _get_validator(registry)
    ir_builder = _get_ir_builder(registry)
    ir_flow = ir_builder.build_flow(flow)
    validator.validate_flow(ir_flow)
    if validator.env_vars:
        requirements.add("python-dotenv>=0.15.0")

    # Detect integrations used in the flow
    used_integrations = set()
    for step in flow.get("steps", []):
        if "action" in step and "." in step["action"]:
            integration, _ = step["action"].split(".", 1)
            if integration not in ("variables", "basic", "control"): # Exclude native/core
                used_integrations.add(integration)
    
    # Add integration-specific requirements from their manifests if registry provides a way
    # For now, this part is simplified. A robust solution would involve the IntegrationHandler
    # or registry providing dependency info for each integration.
    # The existing logic in project_generator.py for this was more complex.
    # This simplified version focuses on what `code_generator.py` can directly infer.
    
    # Example: If integration_handler had a method get_requirements(integration_name)
    # integration_h = _get_integration_handler()
    # for integration_name in used_integrations:
    #     reqs = integration_h.get_requirements(integration_name, "python") # Fictional method
    #     requirements.update(reqs)

    # This part might need to be enhanced if integrations have complex deps not auto-handled by their own setup.
    # For now, we rely on the core ones and python-dotenv.
    
    (project_dir / "requirements.txt").write_text("\n".join(sorted(requirements)) + "\n")

def _create_setup_file(project_dir: Path, package_name: str) -> None:
    """Create a setup.py file for the project."""
    # Read requirements from requirements.txt
    requirements_list = []
    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        with open(req_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    requirements_list.append(f'        "{line}",')
    
    setup_content = f"""from setuptools import setup, find_packages

setup(
    name="{package_name}",
    version="0.1.0",
    description="FlowForge generated project",
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
)
"""
    
    (project_dir / "setup.py").write_text(setup_content)

def _create_run_script(project_dir: Path, package_name: str) -> None:
    """Create a run.sh script for the project."""
    run_script_content = """#!/bin/bash
# Ensure pip is available
if ! command -v pip &> /dev/null
then
    echo "pip could not be found, please install Python and pip."
    exit
fi

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment. Please ensure python3-venv is installed."
        exit 1
    fi
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -e .
if [ $? -ne 0 ]; then
    echo "Failed to install dependencies."
    exit 1
fi

# Run the flow
echo "Running the flow..."
python -m workflow.run
"""
    
    run_path = project_dir / "run.sh"
    run_path.write_text(run_script_content)
    os.chmod(run_path, 0o755)

def _create_run_py(workflow_dir: Path) -> None:
    """Create a run.py module for the project."""
    run_content = """\"\"\"Flow execution script.\"\"\"

from workflow.flow import run_flow
import json
import os # For .env file loading message

def main():
    \"\"\"Execute the flow and return the result.\"\"\"
    if os.path.exists(".env"):
        print("Note: '.env' file found and will be loaded by python-dotenv if 'load_dotenv()' is called in flow.py.")
    elif os.path.exists("../.env"): # If run from within workflow dir
         print("Note: '../.env' file found and will be loaded by python-dotenv if 'load_dotenv()' is called in flow.py.")


    try:
        result = run_flow()
        
        # Try to make result JSON-serializable for display
        try:
            result_str = json.dumps(result, indent=2)
            print(f"Flow completed successfully. Result:")
            print(result_str)
        except (TypeError, ValueError):
            print(f"Flow completed successfully. Result (not JSON serializable): {result}")
            
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

def _detect_env_vars(flow: Dict[str, Any]) -> Set[str]:
    """
    Detect environment variables used in a flow.
    Note: This is a simplified version. The IR-based validation (`validator.env_vars`)
    is more robust and should be preferred. This function is kept for contexts
    where IR might not be built yet or for quick checks on the raw flow dict.
    """
    env_vars = set()
    
    # Check for variables.get_env steps
    for step in flow.get("steps", []):
        if step.get("action") == "variables.get_env":
            env_name = step.get("inputs", {}).get("name")
            if env_name and isinstance(env_name, str): # Ensure env_name is a string literal
                env_vars.add(env_name)
    
    # Check all inputs for template strings with env variables
    for step in flow.get("steps", []):
        for input_name, input_value in step.get("inputs", {}).items():
            if isinstance(input_value, str):
                # Check for {{env.VAR_NAME}} pattern
                matches = re.findall(r'\{\{(?:\s*env\.)([a-zA-Z0-9_]+)(?:\s*)\}\}', input_value)
                env_vars.update(matches)
                
                # Check for {env.VAR_NAME} pattern
                matches = re.findall(r'\{(?:\s*env\.)([a-zA-Z0-9_]+)(?:\s*)\}', input_value)
                env_vars.update(matches)
    
    return env_vars