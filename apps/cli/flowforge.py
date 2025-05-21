"""Updated FlowForge CLI with improved variable management and flow execution."""

import os
import sys
import json
import yaml
import click
from pathlib import Path
import uuid
import time
import shutil
import copy
import re
# asyncio currently not used for core execution, but good for potential async integrations
import asyncio
from typing import List, Dict, Any, Union, Optional
from datetime import datetime, timedelta, timezone


# Add parent directory to path to allow importing core modules
sys.path.append(str(Path(__file__).parent.parent))

from packages.core.registry import Registry
from packages.codegen.code_generator import generate_mermaid, generate_python

# Import the code generation functionality
from packages.codegen.project_generator import generate_project

from packages.core.engine import FlowEngine


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parses a simple duration string (e.g., "5s", "10m", "1h") into a timedelta."""
    if not isinstance(duration_str, str):
        return None
    match = re.fullmatch(r"(\d+)([smh])", duration_str.lower())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2)
    if unit == 's':
        return timedelta(seconds=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    elif unit == 'h':
        return timedelta(hours=value)
    return None

# CLI Commands
@click.group()
def cli():
    """FlowForge CLI tool for AI-guided flow building."""
    pass

@cli.command()
@click.argument('flow_file', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
def plan(flow_file):
    """Generate a plan (Mermaid diagram and Python code) for a flow."""
    with open(flow_file, 'r') as f:
        flow = yaml.safe_load(f)

    registry = Registry()
    registry.load_integrations()

    mermaid = generate_mermaid(flow)
    print("\n--- Mermaid Diagram ---")
    print(mermaid)

    python_code = generate_python(flow, registry)
    print("\n--- Python Code ---")
    print(python_code)

@cli.command("generate-flow")
@click.argument('request', type=str)
@click.option('--output', '-o', type=click.Path(), help='Output file for the generated flow')
@click.option('--model', '-m', type=str, default='anthropic/claude-3.5-sonnet', help='AI model to use')
@click.option('--run', '-r', is_flag=True, help='Run the flow after generating it')
@click.option('--interactive/--no-interactive', '-i/-n', default=True, help='Enable interactive clarification')
@click.option('--debug', is_flag=True, help='Enable debug mode for planner.')
def generate_flow_command(request, output, model, run, interactive, debug):
    """Generate a flow definition from a natural language request."""
    try:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            click.echo("Error: OPENROUTER_API_KEY environment variable not set.", err=True)
            return

        original_flowforge_debug = os.environ.get("FLOWFORGE_DEBUG")
        if debug:
            os.environ["FLOWFORGE_DEBUG"] = "1"

        click.echo(f"Analyzing request: '{request}' using model '{model}'")

        registry = Registry()
        registry.load_integrations()

        from planners.openrouter import openrouter as openrouter_planner_module
        from planners.openrouter import interactive as interactive_planner_module

        api = openrouter_planner_module.OpenRouterAPI(api_key=api_key)
        result_data: Optional[Dict[str, Any]] = None

        if interactive:
            click.echo("Using interactive flow generation...")
            generator = interactive_planner_module.InteractiveFlowGenerator(api, registry)
            analysis = generator.analyze_request(request)

            if not analysis.get("clear_enough", True):
                click.echo(f"\nSuggested flow: {analysis.get('suggested_flow_description', 'N/A')}")
                answers = generator.ask_clarifying_questions(analysis)
                click.echo("\nGenerating flow with clarifications...")
                result_data = generator.generate_flow(request, answers)
            else:
                click.echo("\nRequest seems clear. Generating flow directly...")
                result_data = generator.generate_flow(request)
        else:
            click.echo("Using non-interactive flow generation...")
            result_data = openrouter_planner_module.create_flow(request, list(registry.integrations.keys()), output_format="yaml")

        if not result_data or "flow_definition" not in result_data:
            click.echo("Failed to generate flow definition.", err=True)
            if result_data and "raw_llm_response" in result_data :
                 click.echo(f"LLM Raw Response (or error): {str(result_data['raw_llm_response'])[:500]}...", err=True)
            elif result_data:
                 click.echo(f"Planner result (no flow_definition): {result_data}", err=True)
            return

        flow_yaml_content = result_data["flow_definition"]
        output_path: Path
        if not output:
            flows_dir = DEFAULT_FLOWS_DIR
            flows_dir.mkdir(exist_ok=True)
            safe_name = "".join(c if c.isalnum() else "_" for c in request[:20].lower())
            output_path = flows_dir / f"{safe_name}_{uuid.uuid4().hex[:8]}.yaml"
        else:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            f.write(flow_yaml_content)
        click.echo(f"\nFlow definition saved to: {output_path.resolve()}")

        if "explanation" in result_data: click.echo(f"\n--- Flow Explanation ---\n{result_data['explanation']}")
        if "mermaid_diagram" in result_data: click.echo(f"\n--- Mermaid Diagram ---\n{result_data['mermaid_diagram']}")
        if "python_code" in result_data: click.echo(f"\n--- Python Code ---\n{result_data['python_code']}")

        click.echo(f"\nTo run this flow: python cli/flowforge.py run \"{output_path.resolve()}\"")

        if run:
            click.echo("\nRunning generated flow automatically...")
            time.sleep(0.5)
            # Use click.Context().invoke to call another command
            ctx = click.get_current_context()
            ctx.invoke(run_flow_command_entry, flow_file_path_str=str(output_path.resolve()), flow_inputs_str=None, debug=debug)

    except Exception as e:
        click.echo(f"Error generating flow: {type(e).__name__} - {e}", err=True)
        if debug or os.environ.get("FLOWFORGE_DEBUG") == "1":
            import traceback
            traceback.print_exc()
    finally: # Restore original debug state
        if original_flowforge_debug is None:
            os.environ.pop("FLOWFORGE_DEBUG", None)
        else:
            os.environ["FLOWFORGE_DEBUG"] = original_flowforge_debug


@cli.command("run")
@click.argument('flow_file_path_str', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option('--inputs', '-i', 'flow_inputs_str', type=str, help='JSON string or path to JSON file for flow inputs.')
@click.option('--debug', is_flag=True, help='Enable debug mode for flow engine.')
def run_flow_command_entry(flow_file_path_str, flow_inputs_str, debug):
    """Execute a flow from a YAML file, optionally with JSON inputs."""
    flow_inputs_dict: Optional[Dict[str, Any]] = None
    if flow_inputs_str:
        try:
            inputs_path = Path(flow_inputs_str)
            if inputs_path.exists() and inputs_path.is_file():
                with open(inputs_path, 'r') as f:
                    flow_inputs_dict = json.load(f)
                click.echo(f"Loaded flow inputs from file: {inputs_path}")
            else:
                flow_inputs_dict = json.loads(flow_inputs_str)
                click.echo(f"Parsed flow inputs from string.")
        except json.JSONDecodeError:
            click.echo(f"Error: --inputs value '{flow_inputs_str}' is not valid JSON nor a path to a JSON file.", err=True)
            return
        except Exception as e:
            click.echo(f"Error processing --inputs: {e}", err=True)
            return

    original_flowforge_debug = os.environ.get("FLOWFORGE_DEBUG")
    if debug:
        os.environ["FLOWFORGE_DEBUG"] = "1" # For planner if it's called by an action

    try:
        flow_file_path_obj = Path(flow_file_path_str)
        registry = Registry()
        registry.load_integrations()

        engine = FlowEngine(registry, debug_mode=debug, base_flows_path=flow_file_path_obj.parent)
        engine.execute_flow(flow_file_path_obj, flow_inputs=flow_inputs_dict)

    except Exception as e:
        click.echo(f"Error executing flow '{flow_file_path_str}': {type(e).__name__} - {e}", err=True)
        if debug or os.environ.get("FLOWFORGE_DEBUG") == "1":
            import traceback
            traceback.print_exc()
    finally: # Restore original debug state
        if original_flowforge_debug is None:
            os.environ.pop("FLOWFORGE_DEBUG", None)
        else:
            os.environ["FLOWFORGE_DEBUG"] = original_flowforge_debug


@cli.command("variables")
@click.argument('flow_file_path_str', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option('--env', '-e', is_flag=True, help='Show environment variables.')
@click.option('--local', '-l', is_flag=True, help='Show local flow variables.')
@click.option('--set', '-s', 'var_to_set', help='Set a local variable (format: name=value).')
@click.option('--debug', is_flag=True, help='Enable debug mode.')
def variables_command(flow_file_path_str, env, local, var_to_set, debug):
    """Inspect and manage flow variables."""
    try:
        flow_file_path_obj = Path(flow_file_path_str)
        registry = Registry()
        registry.load_integrations()

        engine = FlowEngine(registry, debug_mode=debug, base_flows_path=flow_file_path_obj.parent)
        
        # Show both by default if neither is specified
        if not env and not local:
            env = True
            local = True
            
        # Display environment variables
        if env:
            click.echo("\nEnvironment Variables:")
            for name, value in sorted(engine.environment.items()):
                # Filter out common but noisy env vars
                if not name.startswith(('_', 'LESSCLOSE', 'LS_COLORS')):
                    click.echo(f"  env.{name} = {value}")
        
        # Display local variables
        if local:
            click.echo("\nLocal Flow Variables:")
            for name, value in sorted(engine.flow_variables.items()):
                click.echo(f"  {name} = {repr(value)}")
        
        # Set variable if requested
        if var_to_set:
            if '=' in var_to_set:
                name, value_str = var_to_set.split('=', 1)
                name = name.strip()
                value_str = value_str.strip()
                
                # Try to evaluate value as Python expression
                try:
                    value = eval(value_str, {"__builtins__": {}}, {})
                except:
                    value = value_str
                
                engine.flow_variables[name] = value
                click.echo(f"\nSet local variable: {name} = {repr(value)}")
            else:
                click.echo(f"Error: Invalid format for --set. Use name=value format.")
        
        # Interactive mode if no specific operation requested
        if not any([env, local, var_to_set]):
            click.echo("\nVariable Editor (enter 'quit' to exit, 'env.VAR' for environment, 'VAR' for local):")
            while True:
                cmd = input("> ").strip()
                if cmd.lower() in ('quit', 'exit', 'q'):
                    break
                
                try:
                    if '=' in cmd:
                        # Set variable
                        name, value_str = cmd.split('=', 1)
                        name = name.strip()
                        value_str = value_str.strip()
                        
                        if name.startswith('env.'):
                            env_name = name[4:]
                            engine.environment[env_name] = value_str
                            click.echo(f"Set environment variable: {env_name} = {value_str}")
                        else:
                            # Try to evaluate value as Python expression for local vars
                            try:
                                value = eval(value_str, {"__builtins__": {}}, {})
                            except:
                                value = value_str
                            
                            engine.flow_variables[name] = value
                            click.echo(f"Set local variable: {name} = {repr(value)}")
                    else:
                        # Get variable
                        name = cmd.strip()
                        if name.startswith('env.'):
                            env_name = name[4:]
                            value = engine.environment.get(env_name, "<undefined>")
                            click.echo(f"env.{env_name} = {value}")
                        elif name:
                            value = engine.flow_variables.get(name, "<undefined>")
                            click.echo(f"{name} = {repr(value)}")
                except Exception as e:
                    click.echo(f"Error: {str(e)}")
                    
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        if debug:
            import traceback
            traceback.print_exc()


@cli.command()
@click.option('--port', '-p', type=int, default=8000, help='Port to run the server on')
def serve(port):
    """Start a simple web server for the FlowForge UI."""
    try:
        from http.server import HTTPServer, SimpleHTTPRequestHandler
        import threading
        import webbrowser

        ui_dir = Path(__file__).parent.parent / "ui"
        if not ui_dir.exists() or not ui_dir.is_dir():
            click.echo(f"Error: UI directory not found or not a directory at {ui_dir}", err=True)
            return

        os.chdir(ui_dir)

        server = HTTPServer(('localhost', port), SimpleHTTPRequestHandler)

        click.echo(f"FlowForge UI server starting at http://localhost:{port}")
        click.echo("Serving files from: " + str(ui_dir))
        click.echo("Press Ctrl+C to stop.")

        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        time.sleep(0.5)
        try: webbrowser.open(f"http://localhost:{port}")
        except Exception as e_wb: click.echo(f"Could not open web browser: {e_wb}")

        while server_thread.is_alive():
            time.sleep(0.5)

    except KeyboardInterrupt:
        click.echo("\nShutting down server...")
        if 'server' in locals() and hasattr(server, 'shutdown'):
            server.shutdown()
            server.server_close()
    except Exception as e:
        click.echo(f"Error starting server: {type(e).__name__} - {e}", err=True)


@cli.command("list-integrations")
def list_integrations_command():
    """List all available integrations and their actions."""
    registry = Registry()
    registry.load_integrations()

    if not registry.integrations:
        click.echo("No integrations found or loaded.")
        return

    for int_name, int_data in registry.integrations.items():
        click.echo(f"\n=== Integration: {click.style(int_name, fg='cyan')} ===")
        desc = int_data.get('description', 'No description.')
        click.echo(f"    {desc}")

        actions = int_data.get('actions', {})
        if not actions:
            click.echo("    No actions defined for this integration.")
            continue

        for act_name, act_data in actions.items():
            click.echo(f"  - Action: {click.style(act_name, fg='green')}")
            act_desc = act_data.get('description', 'No description.')
            click.echo(f"    Description: {act_desc}")

            inputs_data = act_data.get('inputs')
            if inputs_data and isinstance(inputs_data, dict):
                click.echo("    Inputs:")
                for in_name, in_def_or_type in inputs_data.items():
                    in_def = in_def_or_type if isinstance(in_def_or_type, dict) else {"type": str(in_def_or_type)}
                    is_req = in_def.get('required', False)
                    in_type = in_def.get('type', 'any')
                    in_desc = in_def.get('description', '')
                    default_val = f", default: {repr(in_def['default'])}" if 'default' in in_def else ''
                    click.echo(f"      - {in_name} ({in_type}{', required' if is_req else ''}{default_val}): {in_desc}")

            outputs_data = act_data.get('outputs')
            if outputs_data and isinstance(outputs_data, dict):
                click.echo("    Outputs:")
                for out_name, out_type_or_def in outputs_data.items():
                    if isinstance(out_type_or_def, dict):
                        out_type = out_type_or_def.get('type', 'any')
                        out_desc = out_type_or_def.get('description', '')
                        click.echo(f"      - {out_name} ({out_type}): {out_desc}")
                    else:
                        click.echo(f"      - {out_name} ({out_type_or_def})")


@cli.command("generate-code")
@click.argument('flow_file_path_str', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option('--output-dir', '-o', type=click.Path(file_okay=False, writable=True), default="generated_project", show_default=True, help='Output directory for the generated project.')
@click.option('--project-name', '-n', type=str, help='Custom project name (defaults to flow ID).')
def generate_code_command(flow_file_path_str, output_dir, project_name):
    """Generate a deployable Python package from a flow YAML file."""

    output_dir_path = Path(output_dir)
    click.echo(f"Generating Python package from flow: {flow_file_path_str}")

    try:
        registry = Registry()
        registry.load_integrations()

        flow_file_path_obj = Path(flow_file_path_str)
        generated_proj_dir = generate_project(flow_file_path_obj, str(output_dir_path), project_name, registry)

        click.echo(f"\nProject generated successfully at: {generated_proj_dir.resolve()}")
        click.echo("\nTo use the generated project:")
        click.echo(f"  1. cd \"{generated_proj_dir.resolve()}\"")
        click.echo(f"  2. (Optional, create venv): python -m venv .venv && {'source .venv/bin/activate' if os.name != 'nt' else '.venv\\Scripts\\activate'}")
        click.echo(f"  3. pip install -e .")

        run_command = f"python -m workflow.run"
        try: # Try to determine entry point for better instruction
            with open(generated_proj_dir / "setup.py", "r") as f_setup:
                setup_content = f_setup.read()
                pkg_name_match = re.search(r"name\s*=\s*[\"']([^\"']+)[\"']", setup_content)
                if pkg_name_match:
                    entry_point_name = pkg_name_match.group(1)
                    if f"{entry_point_name}=workflow.run:main" in setup_content:
                         run_command = entry_point_name
        except Exception: pass # Ignore if setup.py parsing fails, use default

        click.echo(f"  4. {run_command}")
    except Exception as e:
        click.echo(f"Error generating project: {type(e).__name__} - {e}", err=True)
        sys.exit(1)

if __name__ == '__main__':
    DEFAULT_FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    cli()