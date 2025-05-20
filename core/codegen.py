"""Improved code generation with better variable handling and environment variable support."""

import yaml
from typing import Dict, Any, List, Set, Optional, Union
import re
from pathlib import Path
import os

# The set of control actions we handle specially
CONTROL_ACTIONS = {
    'control.if_node', 'control.if', 'control.switch', 'control.for_each', 'control.while_loop', 'control.while',
    'control.parallel', 'control.merge', 'control.delay', 'control.wait_for',
    'control.try_catch', 'control.try', 'control.retry', 'control.subflow', 'control.terminate'
}

# Special inputs for control actions that reference other steps
CONTROL_STEP_REFS = {
    'control.if_node': ['then_step', 'else_step'],
    'control.if': ['then_step', 'else_step'],
    'control.switch': ['cases', 'default'],
    'control.for_each': ['subflow'],
    'control.while_loop': ['subflow'],
    'control.while': ['subflow'],
    'control.parallel': ['branches'],
    'control.merge': ['sources'],
    'control.try_catch': ['subflow', 'on_error'],
    'control.try': ['try_body', 'catch_handler', 'finally_handler'],
    'control.retry': ['action_step'],
    'control.subflow': ['flow_id', 'flow_ref'],
}

# Variable operations we can handle natively without importing the variables module
NATIVE_VARIABLE_OPS = {
    'variables.get_local', 'variables.set_local', 
    'variables.get_env', 'variables.get', 'variables.set'
}

def generate_mermaid(flow: Dict[str, Any]) -> str:
    """
    Generate a Mermaid graph diagram from a flow definition,
    with special handling for control flow structures.
    
    Args:
        flow: Flow definition dictionary
        
    Returns:
        String containing Mermaid diagram code
    """
    lines = ["graph TD"]
    steps = flow.get('steps', [])
    
    # First, render all nodes
    for step in steps:
        sid = step['id']
        action = step.get('action', '')
        label = action.split('.')[-1] if '.' in action else action
        
        # Use different shapes for control nodes
        if action.startswith('control.'):
            lines.append(f'    {sid}["{sid}: {label}"]')
        elif action.startswith('variables.'):
            lines.append(f'    {sid}["{sid}: {label}"]')
        else:
            lines.append(f'    {sid}("{sid}: {label}")')
    
    # Then, render edges
    for i, step in enumerate(steps):
        sid = step['id']
        action = step.get('action', '')
        inputs = step.get('inputs', {})
        
        # Special handling for different control structures
        if action in ('control.if_node', 'control.if'):
            then_id = inputs.get('then_step')
            if then_id:
                lines.append(f'    {sid} -->|true| {then_id}')
            else_id = inputs.get('else_step')
            if else_id:
                lines.append(f'    {sid} -->|false| {else_id}')
        
        elif action == 'control.switch':
            cases = inputs.get('cases', {})
            if isinstance(cases, dict):
                for case_val, target_id in cases.items():
                    lines.append(f'    {sid} -->|{case_val}| {target_id}')
            default = inputs.get('default')
            if default:
                lines.append(f'    {sid} -->|default| {default}')
        
        elif action in ('control.for_each', 'control.while_loop', 'control.while'):
            subflow = inputs.get('subflow', [])
            if isinstance(subflow, list) and subflow:
                # Check if this is a list of step IDs or step definitions
                if all(isinstance(item, str) for item in subflow):
                    for sub_id in subflow:
                        lines.append(f'    {sid} -->|iteration| {sub_id}')
                elif all(isinstance(item, dict) and 'id' in item for item in subflow):
                    for sub_step in subflow:
                        sub_id = sub_step['id']
                        lines.append(f'    {sid} -->|iteration| {sub_id}')
            elif isinstance(subflow, str):
                lines.append(f'    {sid} -->|iteration| {subflow}')
        
        # Standard sequential flow - connect to next step if not a control structure
        elif not action.startswith('control.') and i < len(steps) - 1:
            next_step = steps[i + 1]
            next_id = next_step['id']
            lines.append(f'    {sid} --> {next_id}')
        
        # For all steps: show data dependencies
        for input_name, input_value in inputs.items():
            if isinstance(input_value, str) and '.' in input_value and not '{' in input_value:
                # Direct reference to another step's output
                source_id, _ = input_value.split('.', 1)
                if source_id in [s['id'] for s in steps]:
                    lines.append(f'    {source_id} -.->|data| {sid}')
    
    return '\n'.join(lines)


def _process_template_string(template: str, step_var: Dict[str, str], context_id: Optional[str] = None) -> str:
    """
    Process a template string with references to other step outputs and variables.
    
    Args:
        template: Template string with {step.output} or {{var}} references
        step_var: Mapping of step IDs to variable names
        context_id: Optional ID of the current context (e.g., within a loop)
        
    Returns:
        Formatted f-string with proper variable references
    """
    if not isinstance(template, str):
        return repr(template)
    
    # Don't process strings without templates
    if not ('{' in template and '}' in template):
        return repr(template)
    
    # Handle different template styles
    
    # Style 1: Double braces for variables and expressions {{var}}
    double_brace_pattern = r'\{\{([^{}]+)\}\}'
    double_matches = re.findall(double_brace_pattern, template)
    
    # Style 2: Single braces for step references {step.output}
    single_brace_pattern = r'(?<!\{)\{([^{}]+)\}(?!\})'
    single_matches = re.findall(single_brace_pattern, template)
    
    # Copy the template for modification
    result_template = template
    
    # Process double brace references (variables and expressions)
    for match in double_matches:
        placeholder = f"{{{{{match}}}}}"
        expression = match.strip()
        
        # Handle different variable types
        if expression.startswith('env.'):
            # Environment variable reference
            env_var = expression[4:]
            replacement = f"{{os.environ.get('{env_var}', '')}}"
        
        elif expression.startswith('var.') or expression.startswith('local.'):
            # Local variable reference
            var_name = expression.split('.', 1)[1]
            replacement = f"{{flow_variables.get('{var_name}', '')}}"
        
        elif '.' in expression:
            # Could be a step reference or a complex expression
            parts = expression.split('.', 1)
            step_id, output_path = parts[0], parts[1]
            
            if step_id in step_var:
                # It's a step reference
                var_ref = step_var[step_id]
                replacement = f"{{{var_ref}['{output_path}']}}"
            else:
                # It might be a mathematical expression or other notation
                # Just pass it through as a Python expression
                replacement = f"{{{expression}}}"
        
        else:
            # Simple variable name or expression
            replacement = f"{{flow_variables.get('{expression}', {expression})}}"
        
        result_template = result_template.replace(placeholder, replacement)
    
    # Process single brace references (step outputs)
    for match in single_matches:
        placeholder = f"{{{match}}}"
        
        if '.' in match:
            step_id, output_path = match.split('.', 1)
            
            if context_id and step_id == context_id:
                # Reference to loop context variable
                var_ref = step_var[step_id]
                replacement = f"{{{var_ref}['{output_path}']}}"
            elif step_id in step_var:
                # Reference to regular step output
                var_ref = step_var[step_id]
                replacement = f"{{{var_ref}['{output_path}']}}"
            else:
                # Unknown reference - keep as is
                replacement = placeholder
        else:
            # Not a proper reference - keep as is
            replacement = placeholder
        
        result_template = result_template.replace(placeholder, replacement)
    
    return f"f\"{result_template}\""


def _process_reference(ref: Any, step_var: Dict[str, str], context_id: Optional[str] = None) -> str:
    """
    Convert a string reference like 'step_id.output' to the appropriate Python variable access.
    Returns the raw value if it's not a reference.
    """
    if isinstance(ref, (int, float, bool)):
        return repr(ref)

    # Special handling for environment variable references in dict format
    if isinstance(ref, dict) and '$ref' in ref:
        ref_value = ref['$ref']
        if isinstance(ref_value, str) and ref_value.startswith('env.'):
            env_var = ref_value.split('.', 1)[1]
            return f"os.environ.get('{env_var}', '')"

    if isinstance(ref, str):
        ref = ref.strip()

        # Template string with {{ }} or { } - should be handled by _process_template_string
        template_re = re.search(r'\{\{[^{}]+\}\}|\{[^{}]+\}', ref)
        if template_re and not ref.startswith('{'):
            return _process_template_string(ref, step_var, context_id)

        # Direct reference to another step's output (not in a template)
        if '.' in ref and not ref.startswith(("'", '"')):
            step_id, output_path = ref.split('.', 1)

            # Reference to environment variable
            if step_id == 'env':
                return f"os.environ.get('{output_path}', '')"
            
            # Reference to local variable
            if step_id in ('var', 'local'):
                return f"flow_variables.get('{output_path}', None)"
            
            # Only treat as a step reference if step_id is known
            if not ((context_id and step_id == context_id) or step_id in step_var):
                return repr(ref)  # It's just a literal string

            # Reference to while-loop context variable
            if context_id and step_id == context_id:
                return f"{step_var[step_id]}['{output_path}']"

            # Reference to regular step output
            var_name = step_var.get(step_id, f"{step_id}_result")
            return f"{var_name}['{output_path}']"

        # Quoted string literal or non-reference
        return repr(ref)

    # Fallback: return as-is for non-string types (e.g. dicts, lists)
    return repr(ref)


def _generate_native_control(step: Dict[str, Any], indent: str, step_var: Dict[str, str], flow_steps: List[Dict[str, Any]]) -> List[str]:
    """
    Generate native Python code for control flow structures with variable support.
    
    Args:
        step: Step definition dictionary
        indent: Current indentation string
        step_var: Mapping of step IDs to variable names
        flow_steps: List of all flow steps
        
    Returns:
        List of code lines for the control structure
    """
    sid = step['id']
    action = step['action']
    inputs = step.get('inputs', {})
    var_name = step_var[sid]
    code_lines = []
    
    # Extract control type from action
    control_type = action.split('.', 1)[1]
    
    # Create a lookup dict for steps by ID
    steps_by_id = {s['id']: s for s in flow_steps}
    
    # Handle different control types
    if control_type in ('if_node', 'if'):
        condition = inputs.get('condition', 'True')
        then_step_id = inputs.get('then_step')
        else_step_id = inputs.get('else_step')
        
        # Process condition and any referenced variables
        condition_expr = condition
        # Extract additional variables used in the condition
        condition_vars = {}
        for key, val in inputs.items():
            if key not in ['condition', 'then_step', 'else_step']:
                condition_vars[key] = val
        
        # Format condition expression properly
        if condition in condition_vars:
            condition_expr = _process_reference(condition_vars[condition], step_var)
        else:
            # Process the condition string, replacing variable references
            for var_key, var_val in condition_vars.items():
                var_ref = _process_reference(var_val, step_var)
                # Replace the variable name with its reference
                condition_expr = re.sub(r'\b' + re.escape(var_key) + r'\b', var_ref, condition_expr)
        
        code_lines.append(f"{indent}# If condition for step {sid}")
        code_lines.append(f"{indent}if {condition_expr}:")
        code_lines.append(f"{indent}    {var_name} = {{'result': True}}")
        if then_step_id:
            code_lines.append(f"{indent}    # Execute then branch: {then_step_id}")
        else:
            code_lines.append(f"{indent}    # Condition is true - no explicit next step defined")
        
        if else_step_id:
            code_lines.append(f"{indent}else:")
            code_lines.append(f"{indent}    {var_name} = {{'result': False}}")
            code_lines.append(f"{indent}    # Execute else branch: {else_step_id}")
        
    elif control_type == 'switch':
        value_expr = inputs.get('value', 'None')
        cases = inputs.get('cases', {})
        default = inputs.get('default')
        
        value_ref = _process_reference(value_expr, step_var)
        
        code_lines.append(f"{indent}# Switch statement for step {sid}")
        code_lines.append(f"{indent}switch_value = {value_ref}")
        code_lines.append(f"{indent}matched_case = None")
        
        if isinstance(cases, dict):
            for i, (case_val, target_id) in enumerate(cases.items()):
                case_comparison = f"switch_value == {repr(case_val)}"
                if i == 0:
                    code_lines.append(f"{indent}if {case_comparison}:")
                else:
                    code_lines.append(f"{indent}elif {case_comparison}:")
                
                code_lines.append(f"{indent}    matched_case = {repr(target_id)}")
                code_lines.append(f"{indent}    # Case {case_val} - next step: {target_id}")
            
            if default:
                code_lines.append(f"{indent}else:")
                code_lines.append(f"{indent}    matched_case = {repr(default)}")
                code_lines.append(f"{indent}    # Default case - next step: {default}")
            
            code_lines.append(f"{indent}{var_name} = {{'matched_case': matched_case}}")
        else:
            code_lines.append(f"{indent}# Invalid cases format")
            code_lines.append(f"{indent}{var_name} = {{'matched_case': None}}")
    
    elif control_type in ('while_loop', 'while'):
        condition = inputs.get('condition', 'True')
        subflow = inputs.get('subflow', [])
        max_iterations = inputs.get('max_iterations', 100)
        
        # Process any variables used in the condition
        condition_vars = {}
        for key, val in inputs.items():
            if key not in ['condition', 'subflow', 'max_iterations', 'loop_variable_updater_step', 'loop_variable_updater_output']:
                condition_vars[key] = val
        
        code_lines.append(f"{indent}# While loop for step {sid}")
        
        # Initialize state variables
        code_lines.append(f"{indent}{var_name} = {{")
        code_lines.append(f"{indent}    'iterations_run': 0,")
        code_lines.append(f"{indent}    'results_per_iteration': [],")
        code_lines.append(f"{indent}    'loop_ended_naturally': False")
        for var_key, var_val in condition_vars.items():
            var_val_str = _process_reference(var_val, step_var)
            code_lines.append(f"{indent}    '{var_key}': {var_val_str},")
        code_lines.append(f"{indent}}}")
        
        # Generate the while loop
        if condition in condition_vars:
            condition_expr = f"{var_name}['{condition}']"
        else:
            # Create a condition expression with proper variable references
            condition_expr = condition
            for var_key, var_val in condition_vars.items():
                pattern = r'\b' + re.escape(var_key) + r'\b'
                replacement = f"{var_name}['{var_key}']"
                condition_expr = re.sub(pattern, replacement, condition_expr)
        
        code_lines.append(f"{indent}while {condition_expr} and {var_name}['iterations_run'] < {max_iterations}:")
        code_lines.append(f"{indent}    {var_name}['iterations_run'] += 1")
        code_lines.append(f"{indent}    iteration_results = {{}}")
        
        # Generate code for the subflow steps
        if isinstance(subflow, list):
            # Process list of step IDs or inline step definitions
            for sub_step in subflow:
                if isinstance(sub_step, str):
                    # Reference to an existing step ID
                    if sub_step in steps_by_id:
                        sub_step_def = steps_by_id[sub_step]
                        sub_id = sub_step
                        sub_action = sub_step_def.get('action', '')
                        sub_inputs = sub_step_def.get('inputs', {})
                    else:
                        continue  # Skip invalid reference
                elif isinstance(sub_step, dict) and 'id' in sub_step:
                    # Inline step definition
                    sub_id = sub_step['id']
                    sub_action = sub_step.get('action', '')
                    sub_inputs = sub_step.get('inputs', {})
                else:
                    continue  # Skip invalid step
                
                sub_var = f"{sub_id}_result"
                
                code_lines.append(f"{indent}    # Subflow step: {sub_id}")
                
                # Generate call to the appropriate function based on action
                if '.' in sub_action:
                    integration, func = sub_action.split('.', 1)
                    
                    # Process inputs with special handling for iterator
                    arg_list = []
                    for input_name, input_val in sub_inputs.items():
                        # Standard input processing
                        val_ref = _process_reference(input_val, step_var, sid)
                        arg_list.append(f"{input_name}={val_ref}")
                    
                    args_str = ", ".join(arg_list)
                    
                    # Use module_var based on integration and action name
                    if integration == 'variables':
                        module_var = 'variables_module'
                    else:
                        # Default to the function name or first part before underscore
                        module_var = func.split('_')[0] if '_' in func else func
                    
                    code_lines.append(f"{indent}    {sub_var} = {module_var}.{func}({args_str})")
                    code_lines.append(f"{indent}    iteration_results['{sub_id}'] = {sub_var}")
                    
                    # Update loop state variables if needed
                    updater_step = inputs.get('loop_variable_updater_step')
                    updater_output = inputs.get('loop_variable_updater_output', 'value')
                    
                    if updater_step and sub_id == updater_step:
                        code_lines.append(f"{indent}    # Update loop state variables")
                        # Update all condition variables with the updater output
                        for var_key in condition_vars:
                            code_lines.append(f"{indent}    {var_name}['{var_key}'] = {sub_var}.get('{updater_output}', {var_name}.get('{var_key}'))")
                    
                    # Special handling for variables integration
                    if integration == 'variables' and func.startswith('set_'):
                        var_key = sub_inputs.get('name', '')
                        if var_key in condition_vars:
                            code_lines.append(f"{indent}    # Update loop state from variable change")
                            code_lines.append(f"{indent}    {var_name}['{var_key}'] = {sub_var}.get('value')")
        
        code_lines.append(f"{indent}    {var_name}['results_per_iteration'].append(iteration_results)")
        code_lines.append(f"{indent}{var_name}['loop_ended_naturally'] = not {condition_expr}")
    
    elif control_type == 'for_each':
        list_input = inputs.get('list_variable_name', 'list')
        list_value = inputs.get(list_input, [])
        iterator_name = inputs.get('iterator_name', 'item')
        subflow = inputs.get('subflow', [])
        
        list_ref = _process_reference(list_value, step_var)
        
        code_lines.append(f"{indent}# For-each loop for step {sid}")
        code_lines.append(f"{indent}loop_list = {list_ref}")
        code_lines.append(f"{indent}if not isinstance(loop_list, (list, tuple)):")
        code_lines.append(f"{indent}    try:")
        code_lines.append(f"{indent}        loop_list = list(loop_list)")
        code_lines.append(f"{indent}    except:")
        code_lines.append(f"{indent}        loop_list = []")
        
        code_lines.append(f"{indent}{var_name} = {{")
        code_lines.append(f"{indent}    'iterations_completed': 0,")
        code_lines.append(f"{indent}    'results_per_iteration': [],")
        code_lines.append(f"{indent}}}")
        
        code_lines.append(f"{indent}for _index, {iterator_name}_value in enumerate(loop_list):")
        code_lines.append(f"{indent}    # Set up iteration context")
        code_lines.append(f"{indent}    flow_variables['{iterator_name}'] = {iterator_name}_value")
        code_lines.append(f"{indent}    flow_variables['{iterator_name}_index'] = _index")
        code_lines.append(f"{indent}    {iterator_name}_result = {{'value': {iterator_name}_value, 'index': _index}}")
        code_lines.append(f"{indent}    iteration_results = {{'{iterator_name}': {iterator_name}_value, '_index': _index}}")
        
        # Generate code for the subflow steps - similar to while_loop
        # (implementation omitted for brevity but would follow the same pattern)
        
        code_lines.append(f"{indent}    {var_name}['results_per_iteration'].append(iteration_results)")
        code_lines.append(f"{indent}    {var_name}['iterations_completed'] += 1")
    
    elif control_type in ('try_catch', 'try'):
        # Try-catch implementation (simplified)
        code_lines.append(f"{indent}# Try-catch block for step {sid}")
        code_lines.append(f"{indent}try:")
        code_lines.append(f"{indent}    # Try block implementation would go here")
        code_lines.append(f"{indent}    pass")
        code_lines.append(f"{indent}except Exception as e:")
        code_lines.append(f"{indent}    # Catch block implementation would go here")
        code_lines.append(f"{indent}    flow_variables['__error'] = {{'type': type(e).__name__, 'message': str(e)}}")
        code_lines.append(f"{indent}{var_name} = {{'success': True, 'error_details': None}}")
    
    else:
        # For other control structures, use a function call approach
        code_lines.append(f"{indent}# Control: {control_type}")
        
        # Use the control module consistently
        module_var = "control"
        
        code_lines.append(f"{indent}{var_name} = {module_var}.{control_type}(")
        
        for i, (name, val) in enumerate(inputs.items()):
            formatted_val = _process_reference(val, step_var)
            if i < len(inputs) - 1:
                code_lines.append(f"{indent}    {name}={formatted_val},")
            else:
                code_lines.append(f"{indent}    {name}={formatted_val}")
        
        code_lines.append(f"{indent})")
    
    return code_lines


def generate_python(flow: Dict[str, Any], registry=None, use_native_control=True, output_dir: Optional[Path] = None, import_style: str = "dynamic") -> str:
    """
    Generate Python code from a flow definition with proper variable handling and module functions.
    
    Args:
        flow: Flow definition dictionary
        registry: Optional Registry instance for validation and action implementation lookup
        use_native_control: Whether to use native Python control structures
        output_dir: Directory to write auxiliary files like .env
        import_style: Import style to use, one of "global", "relative", "project", or "dynamic"
        
    Returns:
        String containing generated Python code
    """
    steps = flow.get('steps', [])
    modules_to_import = {}  # Maps integration_name -> set of modules to import
    action_to_module = {}   # Maps action -> {module_name, module_var} for call resolution
    code_lines = []
    env_vars = set()  # Track all environment variables used in the flow
    needs_variables_module = False  # Flag to track if we need to import variables module
    
    # Track the variable name for each step's result
    step_var = {step['id']: f"{step['id']}_result" for step in steps}
    
    # Build dependency graph
    step_refs = {}  # Maps step ID to the steps it references
    step_deps = {}  # Maps step ID to the steps that depend on it
    control_structures = {}  # Maps control step ID to its branch targets
    
    # First pass: collect actions, determine modules needed, and build dependency graph
    for step in steps:
        if 'action' not in step:
            continue
        
        sid = step['id']
        action = step['action']
        inputs = step.get('inputs', {})
        
        # Initialize dependency tracking for this step
        if sid not in step_refs:
            step_refs[sid] = set()
        if sid not in step_deps:
            step_deps[sid] = set()
        
        # Track control flow branches
        if action in CONTROL_ACTIONS and action in CONTROL_STEP_REFS:
            ref_fields = CONTROL_STEP_REFS[action]
            control_targets = []
            
            for field in ref_fields:
                if field in inputs:
                    field_value = inputs[field]
                    
                    # Handle different field types
                    if isinstance(field_value, str):
                        # Direct step reference
                        control_targets.append(field_value)
                    elif isinstance(field_value, dict) and action == 'control.switch':
                        # Switch cases mapping
                        for target in field_value.values():
                            if isinstance(target, str):
                                control_targets.append(target)
                    elif isinstance(field_value, list):
                        # List of step IDs
                        for target in field_value:
                            if isinstance(target, str):
                                control_targets.append(target)
            
            if control_targets:
                control_structures[sid] = control_targets
        
        # Check for environment variable usage in this step
        if action == 'variables.get_env':
            env_name = inputs.get('name')
            if env_name:
                env_vars.add(env_name)
        
        # Skip control module if using native implementations
        if action.startswith('control.') and use_native_control and action in CONTROL_ACTIONS:
            continue
            
        # Skip variables module if we handle all variable ops natively
        if action.startswith('variables.') and action in NATIVE_VARIABLE_OPS:
            continue
            
        # For any variables action not in NATIVE_VARIABLE_OPS, we need the module
        if action.startswith('variables.') and action not in NATIVE_VARIABLE_OPS:
            needs_variables_module = True
        
        # Track input dependencies
        for input_name, input_value in inputs.items():
            # Skip control step references - they're handled separately
            if action in CONTROL_ACTIONS and input_name in CONTROL_STEP_REFS.get(action, []):
                continue
                
            # Look for step output references
            if isinstance(input_value, str) and '.' in input_value and not ('{' in input_value or input_value.startswith(("'", '"'))):
                ref_step_id, _ = input_value.split('.', 1)
                
                # Only add as a dependency if it's a valid step ID
                if ref_step_id in [s['id'] for s in steps]:
                    step_refs[sid].add(ref_step_id)
                    
                    # Create or update the reverse mapping
                    if ref_step_id not in step_deps:
                        step_deps[ref_step_id] = set()
                    step_deps[ref_step_id].add(sid)
            
            # Check for environment variables in templates
            if isinstance(input_value, str):
                # Look for env. references in templates
                env_patterns = re.findall(r'\{\{(?:\s*env\.)([a-zA-Z0-9_]+)(?:\s*)\}\}', input_value)
                env_vars.update(env_patterns)
                
                # Also check for single brace notation
                env_patterns_single = re.findall(r'\{(?:\s*env\.)([a-zA-Z0-9_]+)(?:\s*)\}', input_value)
                env_vars.update(env_patterns_single)
            
            # Check for $ref format environment variable references
            if isinstance(input_value, dict) and '$ref' in input_value:
                ref_value = input_value['$ref']
                if isinstance(ref_value, str) and ref_value.startswith('env.'):
                    env_var = ref_value.split('.', 1)[1]
                    env_vars.add(env_var)
        
        # If integration not tracked yet, initialize it
        if '.' in action:
            integration, action_name = action.split('.', 1)
            
            if integration not in modules_to_import:
                modules_to_import[integration] = set()
            
            # Use registry if available to find the correct module for this action
            module_name = None
            implementation = None
            
            # Try to get implementation info from registry
            if registry:
                if hasattr(registry, 'get_implementation_for_action'):
                    implementation = registry.get_implementation_for_action(action)
                elif hasattr(registry, 'get_module_for_action'):
                    _, module_name = registry.get_module_for_action(action)
            
            # Try to parse implementation string if available
            if implementation and '.' in implementation:
                # Split "messages.post_message" into module "messages" and function "post_message"
                module_name, function_name = implementation.split('.', 1)
            else:
                # Fallback method when implementation info isn't available
                if integration == 'control':
                    # Special case for control
                    module_name = 'control'
                elif integration == 'variables':
                    # Special case for variables
                    module_name = 'variables'
                else:
                    # For other integrations, use the first part of the action as the module
                    module_name = action_name.split('_')[0] if '_' in action_name else action_name
            
            # Track the module for this integration
            modules_to_import[integration].add(module_name)
            
            # Store the mapping from action to module info
            action_to_module[action] = {
                'integration': integration,
                'module_name': module_name, 
                'module_var': module_name,  # Use module name as the variable name
                'implementation': implementation  # Store the original implementation string
            }
    
    # Always include os for environment variables
    code_lines.append("import os")
    
    # Include sys for dynamic path handling if necessary
    if import_style == "dynamic":
        code_lines.append("import sys")
        code_lines.append("from pathlib import Path")
    
    # Include dotenv if environment variables are used
    if env_vars:
        code_lines.append("from dotenv import load_dotenv")
    
    code_lines.append("")
    
    # Add dynamic path resolution if needed
    if import_style == "dynamic":
        code_lines.append("# Dynamic path resolution to find modules regardless of where project is copied")
        code_lines.append("SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))")
        code_lines.append("# Navigate up to the project root based on directory structure")
        code_lines.append("PROJECT_ROOT = SCRIPT_DIR")
        code_lines.append("# Look for the integrations folder at different levels")
        code_lines.append("while PROJECT_ROOT.name and not (PROJECT_ROOT / 'integrations').exists():")
        code_lines.append("    parent = PROJECT_ROOT.parent")
        code_lines.append("    if parent == PROJECT_ROOT:  # Reached filesystem root")
        code_lines.append("        break")
        code_lines.append("    PROJECT_ROOT = parent")
        code_lines.append("if not (PROJECT_ROOT / 'integrations').exists():")
        code_lines.append("    # Fallback: Check if current directory has integrations")
        code_lines.append("    if (Path.cwd() / 'integrations').exists():")
        code_lines.append("        PROJECT_ROOT = Path.cwd()")
        code_lines.append("# Add project root to system path if not already there")
        code_lines.append("if str(PROJECT_ROOT) not in sys.path:")
        code_lines.append("    sys.path.insert(0, str(PROJECT_ROOT))")
        code_lines.append("")
    
    # Generate import statements
    for integration, modules in sorted(modules_to_import.items()):
        for module in sorted(modules):
            if import_style == "relative":
                # Use relative imports
                code_lines.append(f"from .integrations.{integration} import {module}")
            elif import_style == "project":
                # Use project-based imports (assumes flow.id is the project name)
                project_name = flow.get('id', 'flow').split('_')[0]  # Extract a reasonable project name
                code_lines.append(f"from {project_name}.integrations.{integration} import {module}")
            elif import_style == "dynamic":
                # With dynamic imports, we use absolute paths but the sys.path is modified
                code_lines.append(f"from integrations.{integration} import {module}")
            else:
                # Default: global imports
                code_lines.append(f"from integrations.{integration} import {module}")
    
    # Special handling for variables integration - only import if we need non-native operations
    if needs_variables_module:
        if import_style == "relative":
            code_lines.append("from .integrations.variables import variables as variables_module")
        elif import_style == "project":
            project_name = flow.get('id', 'flow').split('_')[0]
            code_lines.append(f"from {project_name}.integrations.variables import variables as variables_module")
        elif import_style == "dynamic":
            code_lines.append("from integrations.variables import variables as variables_module")
        else:
            code_lines.append("from integrations.variables import variables as variables_module")
    
    if modules_to_import or needs_variables_module:
        code_lines.append("")  # blank line after imports
    
    # Start function
    code_lines.append(f"def run_flow():")
    indent = "    "
    
    # Load environment variables
    if env_vars:
        code_lines.append(f"{indent}# Load environment variables from .env file")
        code_lines.append(f"{indent}load_dotenv()")
        code_lines.append("")
    
    # Initialize flow variables storage
    code_lines.append(f"{indent}# Initialize flow variable storage")
    code_lines.append(f"{indent}flow_variables = {{}}")
    code_lines.append("")
    
    # Define our execution plan based on control flow
    def build_execution_plan(steps):
        """Build an execution plan respecting control flow and dependencies."""
        # Start with a linear plan - we'll adjust for control flow
        linear_plan = steps.copy()
        
        # Identify execution branches
        branches = {}
        for i, step in enumerate(steps):
            sid = step['id']
            action = step.get('action', '')
            
            # Handle control flow structures
            if action in ('control.if_node', 'control.if'):
                inputs = step.get('inputs', {})
                then_step = inputs.get('then_step')
                else_step = inputs.get('else_step')
                
                if then_step or else_step:
                    branches[sid] = {
                        'type': 'if',
                        'then': then_step,
                        'else': else_step
                    }
            
            elif action == 'control.switch':
                inputs = step.get('inputs', {})
                cases = inputs.get('cases', {})
                default = inputs.get('default')
                
                if cases or default:
                    branches[sid] = {
                        'type': 'switch',
                        'cases': cases,
                        'default': default
                    }
        
        return linear_plan, branches
    
    # Find a valid step ordering for code generation
    execution_plan, branches = build_execution_plan(steps)
    
    # Generate code for steps with proper control flow branching
    def process_execution_plan(plan, branches, indent="    ", processed=None):
        if processed is None:
            processed = set()
        
        # Keep track of steps generated inside conditional branches
        in_conditional_branch = {}
        
        # Process steps in order
        i = 0
        while i < len(plan):
            step = plan[i]
            sid = step['id']
            
            # Skip if already processed
            if sid in processed:
                i += 1
                continue
                
            action = step.get('action', '')
            inputs = step.get('inputs', {})
            
            # Check if this step is a control structure with branches
            if sid in branches:
                branch_info = branches[sid]
                branch_type = branch_info['type']
                
                # Generate the control structure code
                if branch_type == 'if':
                    # First, create the if condition check
                    control_code = _generate_native_control(step, indent, step_var, steps)
                    code_lines.extend(control_code)
                    code_lines.append("")  # blank line
                    
                    then_step = branch_info['then']
                    else_step = branch_info['else']
                    
                    # Mark this control step as processed
                    processed.add(sid)
                    
                    # Generate nested blocks for then branch
                    if then_step and then_step in [s['id'] for s in plan]:
                        # Find the then_step in the plan
                        then_index = next((j for j, s in enumerate(plan) if s['id'] == then_step), None)
                        
                        if then_index is not None:
                            # Generate nested block for the then branch
                            code_lines.append(f"{indent}if {step_var[sid]}['result']:")  # Check result of the if condition
                            
                            # Process the then step and its following steps
                            then_step_obj = plan[then_index]
                            
                            # Mark which steps will be processed inside this branch
                            in_conditional_branch[then_step] = True
                            
                            # Process the then branch step
                            process_step(then_step_obj, processed, indent + "    ")
                    
                    # Generate nested blocks for else branch
                    if else_step and else_step in [s['id'] for s in plan]:
                        # Find the else_step in the plan
                        else_index = next((j for j, s in enumerate(plan) if s['id'] == else_step), None)
                        
                        if else_index is not None:
                            # Generate nested block for the else branch
                            code_lines.append(f"{indent}if not {step_var[sid]}['result']:")  # Check result of the if condition
                            
                            # Process the else step and its following steps
                            else_step_obj = plan[else_index]
                            
                            # Mark which steps will be processed inside this branch
                            in_conditional_branch[else_step] = True
                            
                            # Process the else branch step
                            process_step(else_step_obj, processed, indent + "    ")
                
                elif branch_type == 'switch':
                    # Similar implementation for switch as for if
                    # First, create the switch evaluation
                    control_code = _generate_native_control(step, indent, step_var, steps)
                    code_lines.extend(control_code)
                    code_lines.append("")  # blank line
                    
                    # Mark this control step as processed
                    processed.add(sid)
                    
                    # Handle case branches
                    cases = branch_info['cases']
                    for case_val, target_id in cases.items():
                        # Find the target step in the plan
                        target_index = next((j for j, s in enumerate(plan) if s['id'] == target_id), None)
                        
                        if target_index is not None:
                            # Generate nested block for this case
                            code_lines.append(f"{indent}if {step_var[sid]}['matched_case'] == {repr(case_val)}:")
                            
                            # Process the target step
                            target_step_obj = plan[target_index]
                            
                            # Mark which steps will be processed inside this branch
                            in_conditional_branch[target_id] = True
                            
                            # Process the case branch step
                            process_step(target_step_obj, processed, indent + "    ")
                    
                    # Handle default branch
                    default = branch_info['default']
                    if default:
                        # Find the default step in the plan
                        default_index = next((j for j, s in enumerate(plan) if s['id'] == default), None)
                        
                        if default_index is not None:
                            # Generate nested block for the default case
                            code_lines.append(f"{indent}if {step_var[sid]}['matched_case'] is None:")
                            
                            # Process the default step
                            default_step_obj = plan[default_index]
                            
                            # Mark which steps will be processed inside this branch
                            in_conditional_branch[default] = True
                            
                            # Process the default branch step
                            process_step(default_step_obj, processed, indent + "    ")
                
                # Move to next step in the plan
                i += 1
            else:
                # Skip steps that are part of conditional branches - they'll be processed there
                if sid in in_conditional_branch:
                    i += 1
                    continue
                
                # Regular step processing (not a control structure)
                process_step(step, processed, indent)
                i += 1
    
    # Process steps with control flow
    def process_step(step, processed=None, indent="    "):
        if processed is None:
            processed = set()
            
        sid = step['id']
        
        # Skip if this step is already processed
        if sid in processed:
            return
            
        processed.add(sid)
        
        action = step.get('action', '')
        
        if action.startswith('control.') and use_native_control and action in CONTROL_ACTIONS:
            # Control steps should be handled by process_execution_plan
            # We only generate the condition check here, not the branching logic
            if action not in ('control.if_node', 'control.if', 'control.switch'):
                # Generate native Python control structures for non-branching controls
                control_code = _generate_native_control(step, indent, step_var, steps)
                code_lines.extend(control_code)
                code_lines.append("")  # blank line after control structure
        
        elif action.startswith('variables.') and action in NATIVE_VARIABLE_OPS:
            # Special handling for variables integration with native implementations
            inputs = step.get('inputs', {})
            var_name = step_var[sid]
            
            code_lines.append(f"{indent}# Variable operation: {sid} ({action})")
            
            # Extract action type and process inputs
            _, func = action.split('.', 1)
            
            # Handle different variable operations natively
            if func == 'get_local':
                var_key = inputs.get('name', '')
                default = inputs.get('default')
                
                if default is None:
                    code_lines.append(f"{indent}{var_name} = {{'value': flow_variables.get({repr(var_key)}, None)}}")
                else:
                    default_val = _process_reference(default, step_var)
                    code_lines.append(f"{indent}{var_name} = {{'value': flow_variables.get({repr(var_key)}, {default_val})}}")
            
            elif func == 'set_local':
                var_key = inputs.get('name', '')
                value = _process_reference(inputs.get('value'), step_var)
                code_lines.append(f"{indent}flow_variables[{repr(var_key)}] = {value}")
                code_lines.append(f"{indent}{var_name} = {{'value': {value}}}")
            
            elif func == 'get_env':
                env_key = inputs.get('name', '')
                default = inputs.get('default')
                
                if default is None:
                    code_lines.append(f"{indent}{var_name} = {{'value': os.environ.get({repr(env_key)}, '')}}")
                else:
                    default_val = _process_reference(default, step_var)
                    code_lines.append(f"{indent}{var_name} = {{'value': os.environ.get({repr(env_key)}, {default_val})}}")
            
            elif func == 'get':
                # Legacy get - check flow variables first, then env
                var_key = inputs.get('name', '')
                default = inputs.get('default')
                
                if default is None:
                    code_lines.append(f"{indent}# Get variable from flow_variables or environment")
                    code_lines.append(f"{indent}if {repr(var_key)} in flow_variables:")
                    code_lines.append(f"{indent}    {var_name} = {{'value': flow_variables.get({repr(var_key)})}}")
                    code_lines.append(f"{indent}else:")
                    code_lines.append(f"{indent}    {var_name} = {{'value': os.environ.get({repr(var_key)}, '')}}")
                else:
                    default_val = _process_reference(default, step_var)
                    code_lines.append(f"{indent}# Get variable from flow_variables or environment with default")
                    code_lines.append(f"{indent}if {repr(var_key)} in flow_variables:")
                    code_lines.append(f"{indent}    {var_name} = {{'value': flow_variables.get({repr(var_key)})}}")
                    code_lines.append(f"{indent}else:")
                    code_lines.append(f"{indent}    {var_name} = {{'value': os.environ.get({repr(var_key)}, {default_val})}}")
            
            elif func == 'set':
                # Legacy set - always sets to flow variables
                var_key = inputs.get('name', '')
                value = _process_reference(inputs.get('value'), step_var)
                code_lines.append(f"{indent}flow_variables[{repr(var_key)}] = {value}")
                code_lines.append(f"{indent}{var_name} = {{'value': {value}}}")
            
            code_lines.append("")  # blank line after step
        
        else:
            # Generate regular function call for non-control, non-native variable steps
            inputs = step.get('inputs', {})
            
            code_lines.append(f"{indent}# Step: {sid} ({action})")
            
            # Regular actions
            if '.' in action:
                integration, action_name = action.split('.', 1)
                
                # Get the module info for this action
                module_info = action_to_module.get(action, {})
                module_var = module_info.get('module_var')
                implementation = module_info.get('implementation')
                
                # If we have implementation info, use it to determine function name
                if implementation and '.' in implementation:
                    module_name, func_name = implementation.split('.', 1)
                else:
                    # Default to using the action name as the function name
                    func_name = action_name
                
                # If this is a variables module action and we're handling variables natively
                if integration == 'variables' and not module_var:
                    module_var = 'variables_module'
                
                # Fallback if mapping not found
                if not module_var:
                    module_var = func_name.split('_')[0] if '_' in func_name else func_name
                
                # Build argument list with variable support
                arg_list = []
                for name, val in inputs.items():
                    formatted_val = _process_reference(val, step_var)
                    arg_list.append(f"{name}={formatted_val}")
                
                args = ", ".join(arg_list)
                var_name = step_var[sid]
                
                # Emit call with correct module variable and function name
                code_lines.append(f"{indent}{var_name} = {module_var}.{func_name}({args})")
            else:
                # Unknown action format - add a comment
                code_lines.append(f"{indent}# Unknown action format: {action}")
                var_name = step_var[sid]
                code_lines.append(f"{indent}{var_name} = {{'status': 'unknown_action'}}")
            
            code_lines.append("")  # blank line after step
    
    # Process the execution plan
    process_execution_plan(execution_plan, branches)
    
    # Return last step's result
    if steps:
        last = steps[-1]['id']
        code_lines.append(f"{indent}return {step_var[last]}")
    else:
        code_lines.append(f"{indent}return None")
    
    result = "\n".join(code_lines)
    
    # Generate .env file if environment variables are used
    if env_vars and output_dir:
        # Ensure we're generating the .env file
        generate_env_file(flow.get('id', 'flow'), env_vars, output_dir)
    elif env_vars:
        # Fallback for backward compatibility
        generate_env_file(flow.get('id', 'flow'), env_vars)
    
    return result


def generate_env_file(flow_id: str, env_vars: Set[str], output_dir: Optional[Path] = None) -> None:
    """
    Generate a .env file with placeholders for detected environment variables.
    
    Args:
        flow_id: ID of the flow
        env_vars: Set of environment variable names used in the flow
        output_dir: Directory to write the .env file (default: current directory)
    """
    if not env_vars:
        return
    
    # Determine where to place the .env file
    if output_dir is None:
        output_dir = Path(".")
    
    # Create .env file in the specified directory
    env_file = output_dir / ".env"
    print(f"Generating .env file at: {env_file}")
    
    # Generate content
    lines = [
        "# Environment variables used in flow: " + flow_id,
        "# Fill in the values below for environment variables used in this flow",
        ""
    ]
    
    for var_name in sorted(env_vars):
        lines.append(f"{var_name}=")
    
    # Write the file
    try:
        with open(env_file, 'w') as f:
            f.write("\n".join(lines))
        print(f"Generated .env template file: {env_file}")
    except Exception as e:
        print(f"Error writing .env file: {str(e)}")


def validate_flow(flow: Dict[str, Any], registry=None) -> List[str]:
    """
    Validate a flow definition against a registry if provided.
    
    Args:
        flow: Flow definition dictionary
        registry: Optional Registry instance
        
    Returns:
        List of validation error messages, empty if no errors
    """
    errors = []
    
    # Basic flow structure validation
    if not isinstance(flow, dict):
        errors.append("Flow definition must be a dictionary")
        return errors
    
    if 'id' not in flow:
        errors.append("Flow is missing required 'id' field")
    
    if 'steps' not in flow or not isinstance(flow.get('steps'), list):
        errors.append("Flow is missing 'steps' list or 'steps' is not a list")
        return errors
    
    steps = flow.get('steps', [])
    step_ids = set()
    
    # Validate each step
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"Step at index {i} is not a dictionary")
            continue
        
        # Check for required step fields
        if 'id' not in step:
            errors.append(f"Step at index {i} is missing required 'id' field")
            continue
        
        step_id = step['id']
        
        # Check for duplicate step IDs
        if step_id in step_ids:
            errors.append(f"Duplicate step ID '{step_id}'")
        else:
            step_ids.add(step_id)
        
        # Check action field
        if 'action' not in step:
            errors.append(f"Step '{step_id}' is missing required 'action' field")
            continue
        
        action = step['action']
        
        # Validate action with registry
        if registry and '.' in action:
            integration, action_name = action.split('.', 1)
            
            # Check if integration exists
            if integration not in registry.integrations:
                errors.append(f"Step '{step_id}' uses unknown integration '{integration}'")
                continue
            
            # Check if action exists in integration
            integration_actions = registry.integrations[integration].get('actions', {})
            if action_name not in integration_actions:
                errors.append(f"Step '{step_id}' uses unknown action '{action_name}' in integration '{integration}'")
                continue
            
            # Validate inputs
            inputs = step.get('inputs', {})
            action_def = integration_actions[action_name]
            action_inputs = action_def.get('inputs', {})
            
            # Check for required inputs
            for input_name, input_def in action_inputs.items():
                if isinstance(input_def, dict) and input_def.get('required', False):
                    if input_name not in inputs:
                        errors.append(f"Step '{step_id}' is missing required input '{input_name}' for action '{action}'")
    
    # Validate control flow references
    for step in steps:
        if 'action' not in step or 'id' not in step:
            continue
        
        step_id = step['id']
        action = step['action']
        
        # Check control flow references
        if action.startswith('control.'):
            control_type = action.split('.', 1)[1]
            inputs = step.get('inputs', {})
            
            # For control.if and control.if_node
            if control_type in ('if', 'if_node'):
                then_step = inputs.get('then_step')
                else_step = inputs.get('else_step')
                
                if then_step and then_step not in step_ids:
                    errors.append(f"Step '{step_id}' references non-existent then_step '{then_step}'")
                if else_step and else_step not in step_ids:
                    errors.append(f"Step '{step_id}' references non-existent else_step '{else_step}'")
            
            # For control.switch
            elif control_type == 'switch':
                cases = inputs.get('cases', {})
                default = inputs.get('default')
                
                if isinstance(cases, dict):
                    for case_val, target_id in cases.items():
                        if target_id not in step_ids:
                            errors.append(f"Step '{step_id}' switch case '{case_val}' references non-existent step '{target_id}'")
                
                if default and default not in step_ids:
                    errors.append(f"Step '{step_id}' switch default references non-existent step '{default}'")
    
    return errors