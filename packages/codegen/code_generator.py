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

# Global variable to track flow variable names
flow_variable_names = set()

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

# Regular expression for strict step.output references
_REF_RE = re.compile(r"^[A-Za-z_][\w-]*\.[\w-]+$")  # strict "step.output"

def _process_reference(
    ref: Any, 
    step_var: Dict[str, str], 
    context_id: Optional[str] = None
) -> str:
    """
    Turn a YAML value into Python code.
    """
    # ── literals ────────────────────────────────────────────────────────────────
    if isinstance(ref, (int, float, bool)) or ref is None:
        return repr(ref)

    # ── $ref environment variables (dict form) ─────────────────────────────────
    if isinstance(ref, dict) and "$ref" in ref:
        target = ref["$ref"]
        if isinstance(target, str) and target.startswith("env."):
            return f"os.environ.get('{target.split('.', 1)[1]}', '')"
        return repr(ref)

    # ── strings ────────────────────────────────────────────────────────────────
    if not isinstance(ref, str):
        return repr(ref)

    ref = ref.strip()

    # 1) template strings ("{…}" or "{{…}}")
    if "{" in ref and "}" in ref and not ref.startswith("{"):
        return _process_template_string(ref, step_var, context_id)

    # 2) step-output reference (must match strict regex, *no* spaces)
    if _REF_RE.match(ref):
        step_id, field = ref.split(".", 1)
        if context_id and step_id == context_id:
            return f"{step_var[step_id]}['{field}']"
        if step_id in step_var:
            return f"{step_var[step_id]}['{field}']"

    # 3) plain flow-variable
    if ref in flow_variable_names and " " not in ref:
        return f"flow_variables.get('{ref}', None)"

    # 4) ordinary literal string
    return repr(ref)


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
            replacement = f"{{flow_variables.get('{expression}', '')}}"
        
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
    
    # Escape real new-lines so the generated code stays on one line
    result_template = result_template.replace("\n", "\\n")
    # Return an f-string (no stray "sum" built-in!)
    return f'f"{result_template}"'


def _process_native_control(step: Dict[str, Any], indent: str, step_var: Dict[str, str], flow_steps: List[Dict[str, Any]]) -> List[str]:
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
            condition_expr = _process_reference(condition_vars[condition], step_var, context_id=sid)
        else:
            # Process the condition string, replacing variable references
            for var_key, var_val in condition_vars.items():
                var_ref = _process_reference(var_val, step_var, context_id=sid)
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
        
        value_ref = _process_reference(value_expr, step_var, context_id=sid)
        
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
            var_val_str = _process_reference(var_val, step_var, context_id=sid)
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
                        val_ref = _process_reference(input_val, step_var, context_id=sid)
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
        
        list_ref = _process_reference(list_value, step_var, context_id=sid)
        
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
                        # Check for special iterator variable references
                        if isinstance(input_val, str) and input_val == iterator_name:
                            arg_list.append(f"{input_name}={iterator_name}_value")
                        elif isinstance(input_val, str) and input_val == f"{iterator_name}.value":
                            arg_list.append(f"{input_name}={iterator_name}_value")
                        elif isinstance(input_val, str) and input_val == f"{iterator_name}.index":
                            arg_list.append(f"{input_name}=_index")
                        else:
                            # Standard input processing
                            val_ref = _process_reference(input_val, step_var, context_id=sid)
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
        
        code_lines.append(f"{indent}    {var_name}['results_per_iteration'].append(iteration_results)")
        code_lines.append(f"{indent}    {var_name}['iterations_completed'] += 1")
    
    elif control_type in ('try_catch', 'try'):
        try_block = inputs.get('subflow', inputs.get('try_body', []))
        catch_block = inputs.get('on_error', inputs.get('catch_handler', []))
        finally_block = inputs.get('finally_handler', [])
        
        code_lines.append(f"{indent}# Try-catch block for step {sid}")
        code_lines.append(f"{indent}{var_name} = {{'success': True, 'error_details': None}}")
        code_lines.append(f"{indent}try:")
        
        # Generate code for the try block
        if isinstance(try_block, list):
            # Process list of step IDs or inline step definitions
            for sub_step in try_block:
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
                
                code_lines.append(f"{indent}    # Try block step: {sub_id}")
                
                # Generate call to the appropriate function based on action
                if '.' in sub_action:
                    integration, func = sub_action.split('.', 1)
                    
                    # Process inputs
                    arg_list = []
                    for input_name, input_val in sub_inputs.items():
                        val_ref = _process_reference(input_val, step_var, context_id=sid)
                        arg_list.append(f"{input_name}={val_ref}")
                    
                    args_str = ", ".join(arg_list)
                    
                    # Use module_var based on integration and action name
                    if integration == 'variables':
                        module_var = 'variables_module'
                    else:
                        # Default to the function name or first part before underscore
                        module_var = func.split('_')[0] if '_' in func else func
                    
                    code_lines.append(f"{indent}    {sub_var} = {module_var}.{func}({args_str})")
        else:
            code_lines.append(f"{indent}    # No try block steps defined")
            code_lines.append(f"{indent}    pass")
        
        # Generate catch block
        code_lines.append(f"{indent}except Exception as e:")
        code_lines.append(f"{indent}    {var_name}['success'] = False")
        code_lines.append(f"{indent}    {var_name}['error_details'] = {{'type': type(e).__name__, 'message': str(e)}}")
        code_lines.append(f"{indent}    flow_variables['__error'] = {{'type': type(e).__name__, 'message': str(e)}}")
        
        if isinstance(catch_block, list) and catch_block:
            # Process catch block steps
            for sub_step in catch_block:
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
                
                code_lines.append(f"{indent}    # Catch block step: {sub_id}")
                
                # Generate call to the appropriate function based on action
                if '.' in sub_action:
                    integration, func = sub_action.split('.', 1)
                    
                    # Process inputs
                    arg_list = []
                    for input_name, input_val in sub_inputs.items():
                        val_ref = _process_reference(input_val, step_var, context_id=sid)
                        arg_list.append(f"{input_name}={val_ref}")
                    
                    args_str = ", ".join(arg_list)
                    
                    # Use module_var based on integration and action name
                    if integration == 'variables':
                        module_var = 'variables_module'
                    else:
                        # Default to the function name or first part before underscore
                        module_var = func.split('_')[0] if '_' in func else func
                    
                    code_lines.append(f"{indent}    {sub_var} = {module_var}.{func}({args_str})")
        else:
            code_lines.append(f"{indent}    # No catch block steps defined")
            code_lines.append(f"{indent}    pass")
        
        # Generate finally block if provided
        if isinstance(finally_block, list) and finally_block:
            code_lines.append(f"{indent}finally:")
            # Process finally block steps
            for sub_step in finally_block:
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
                
                code_lines.append(f"{indent}    # Finally block step: {sub_id}")
                
                # Generate call to the appropriate function based on action
                if '.' in sub_action:
                    integration, func = sub_action.split('.', 1)
                    
                    # Process inputs
                    arg_list = []
                    for input_name, input_val in sub_inputs.items():
                        val_ref = _process_reference(input_val, step_var, context_id=sid)
                        arg_list.append(f"{input_name}={val_ref}")
                    
                    args_str = ", ".join(arg_list)
                    
                    # Use module_var based on integration and action name
                    if integration == 'variables':
                        module_var = 'variables_module'
                    else:
                        # Default to the function name or first part before underscore
                        module_var = func.split('_')[0] if '_' in func else func
                    
                    code_lines.append(f"{indent}    {sub_var} = {module_var}.{func}({args_str})")
            
            # Cleanup flow variables
            code_lines.append(f"{indent}    # Clean up error flow variable")
            code_lines.append(f"{indent}    if '__error' in flow_variables:")
            code_lines.append(f"{indent}        del flow_variables['__error']")
    
    elif control_type == 'parallel':
        branches = inputs.get('branches', [])
        wait_for_all = inputs.get('wait_for_all', True)
        
        code_lines.append(f"{indent}# Parallel execution for step {sid}")
        code_lines.append(f"{indent}{var_name} = {{")
        code_lines.append(f"{indent}    'branches_executed': 0,")
        code_lines.append(f"{indent}    'outputs_per_branch': [],")
        code_lines.append(f"{indent}    'wait_for_all': {wait_for_all}")
        code_lines.append(f"{indent}}}")
        
        code_lines.append(f"{indent}# Note: This is a sequential simulation of parallel execution")
        
        # Process each branch
        for i, branch in enumerate(branches):
            code_lines.append(f"{indent}# Branch {i+1}")
            code_lines.append(f"{indent}branch_{i}_results = {{}}")
            
            # Process steps in this branch
            if isinstance(branch, list):
                for branch_step in branch:
                    if isinstance(branch_step, str):
                        # Reference to an existing step ID
                        if branch_step in steps_by_id:
                            branch_step_def = steps_by_id[branch_step]
                            branch_id = branch_step
                            branch_action = branch_step_def.get('action', '')
                            branch_inputs = branch_step_def.get('inputs', {})
                        else:
                            continue  # Skip invalid reference
                    elif isinstance(branch_step, dict) and 'id' in branch_step:
                        # Inline step definition
                        branch_id = branch_step['id']
                        branch_action = branch_step.get('action', '')
                        branch_inputs = branch_step.get('inputs', {})
                    else:
                        continue  # Skip invalid step
                    
                    branch_var = f"{branch_id}_result"
                    
                    code_lines.append(f"{indent}# Branch {i+1} step: {branch_id}")
                    
                    # Generate call to the appropriate function based on action
                    if '.' in branch_action:
                        integration, func = branch_action.split('.', 1)
                        
                        # Process inputs
                        arg_list = []
                        for input_name, input_val in branch_inputs.items():
                            val_ref = _process_reference(input_val, step_var, context_id=sid)
                            arg_list.append(f"{input_name}={val_ref}")
                        
                        args_str = ", ".join(arg_list)
                        
                        # Use module_var based on integration and action name
                        if integration == 'variables':
                            module_var = 'variables_module'
                        else:
                            # Default to the function name or first part before underscore
                            module_var = func.split('_')[0] if '_' in func else func
                        
                        code_lines.append(f"{indent}{branch_var} = {module_var}.{func}({args_str})")
                        code_lines.append(f"{indent}branch_{i}_results['{branch_id}'] = {branch_var}")
            
            code_lines.append(f"{indent}{var_name}['outputs_per_branch'].append(branch_{i}_results)")
            code_lines.append(f"{indent}{var_name}['branches_executed'] += 1")
    
    elif control_type == 'delay':
        seconds = inputs.get('seconds', 0)
        seconds_value = _process_reference(seconds, step_var, context_id=sid)
        
        code_lines.append(f"{indent}# Delay execution for step {sid}")
        code_lines.append(f"{indent}import time")
        code_lines.append(f"{indent}seconds_to_delay = {seconds_value}")
        code_lines.append(f"{indent}if isinstance(seconds_to_delay, str):")
        code_lines.append(f"{indent}    try:")
        code_lines.append(f"{indent}        seconds_to_delay = float(seconds_to_delay)")
        code_lines.append(f"{indent}    except (ValueError, TypeError):")
        code_lines.append(f"{indent}        seconds_to_delay = 0")
        code_lines.append(f"{indent}elif not isinstance(seconds_to_delay, (int, float)):")
        code_lines.append(f"{indent}    seconds_to_delay = 0")
        code_lines.append(f"{indent}if seconds_to_delay > 0:")
        code_lines.append(f"{indent}    time.sleep(seconds_to_delay)")
        code_lines.append(f"{indent}{var_name} = {{'delayed_for_seconds': seconds_to_delay, 'completed': True}}")
    
    elif control_type == 'wait_for':
        event = inputs.get('event', inputs.get('until', 'None'))
        timeout = inputs.get('timeout', '60s')
        
        event_value = _process_reference(event, step_var, context_id=sid)
        timeout_value = _process_reference(timeout, step_var, context_id=sid)
        
        code_lines.append(f"{indent}# Wait for event/condition for step {sid}")
        code_lines.append(f"{indent}import time")
        code_lines.append(f"{indent}from datetime import datetime, timedelta")
        code_lines.append(f"{indent}event_value = {event_value}")
        code_lines.append(f"{indent}timeout_value = {timeout_value}")
        code_lines.append(f"{indent}# Parse the event value to determine wait strategy")
        code_lines.append(f"{indent}wait_seconds = 0")
        code_lines.append(f"{indent}is_duration = False")
        code_lines.append(f"{indent}# Check if it's a simple duration in seconds")
        code_lines.append(f"{indent}if isinstance(event_value, (int, float)):")
        code_lines.append(f"{indent}    wait_seconds = float(event_value)")
        code_lines.append(f"{indent}    is_duration = True")
        code_lines.append(f"{indent}# Check for duration strings like '5s', '10m', '1h'")
        code_lines.append(f"{indent}elif isinstance(event_value, str):")
        code_lines.append(f"{indent}    import re")
        code_lines.append(f"{indent}    duration_match = re.fullmatch(r'(\\d+)([smh])', event_value)")
        code_lines.append(f"{indent}    if duration_match:")
        code_lines.append(f"{indent}        value, unit = int(duration_match.group(1)), duration_match.group(2)")
        code_lines.append(f"{indent}        if unit == 's':")
        code_lines.append(f"{indent}            wait_seconds = value")
        code_lines.append(f"{indent}        elif unit == 'm':")
        code_lines.append(f"{indent}            wait_seconds = value * 60")
        code_lines.append(f"{indent}        elif unit == 'h':")
        code_lines.append(f"{indent}            wait_seconds = value * 3600")
        code_lines.append(f"{indent}        is_duration = True")
        code_lines.append(f"{indent}    else:")
        code_lines.append(f"{indent}        # Check if it's a timestamp")
        code_lines.append(f"{indent}        try:")
        code_lines.append(f"{indent}            target_time = datetime.fromisoformat(event_value.rstrip('Z'))")
        code_lines.append(f"{indent}            current_time = datetime.now()")
        code_lines.append(f"{indent}            if target_time > current_time:")
        code_lines.append(f"{indent}                wait_seconds = (target_time - current_time).total_seconds()")
        code_lines.append(f"{indent}                is_duration = True")
        code_lines.append(f"{indent}        except (ValueError, AttributeError):")
        code_lines.append(f"{indent}            pass")
        code_lines.append(f"{indent}# Perform the wait")
        code_lines.append(f"{indent}if is_duration and wait_seconds > 0:")
        code_lines.append(f"{indent}    time.sleep(wait_seconds)")
        code_lines.append(f"{indent}    {var_name} = {{'event_triggered': True, 'condition_met': True, 'waited_seconds': wait_seconds}}")
        code_lines.append(f"{indent}else:")
        code_lines.append(f"{indent}    # For non-duration events, simulate that the event occurred immediately")
        code_lines.append(f"{indent}    {var_name} = {{'event_triggered': True, 'condition_met': True, 'simulated': True}}")
    
    elif control_type == 'retry':
        action_step_id = inputs.get('action_step')
        attempts = inputs.get('attempts', 3)
        backoff_seconds = inputs.get('backoff_seconds', 0)
        
        attempts_value = _process_reference(attempts, step_var, context_id=sid)
        backoff_value = _process_reference(backoff_seconds, step_var, context_id=sid)
        
        code_lines.append(f"{indent}# Retry logic for step {sid}")
        code_lines.append(f"{indent}import time")
        code_lines.append(f"{indent}{var_name} = {{")
        code_lines.append(f"{indent}    'action_succeeded': False,")
        code_lines.append(f"{indent}    'attempts_made': 0,")
        code_lines.append(f"{indent}    'last_action_result': None")
        code_lines.append(f"{indent}}}")
        
        # Make sure we can find the step to retry
        code_lines.append(f"{indent}# Find the step to retry")
        code_lines.append(f"{indent}if '{action_step_id}' in globals():")
        code_lines.append(f"{indent}    action_step_id = '{action_step_id}'")
        code_lines.append(f"{indent}else:")
        code_lines.append(f"{indent}    raise ValueError(f\"Retry step '{sid}' references non-existent action step '{action_step_id}'\")")
        
        # Process the max attempts input
        code_lines.append(f"{indent}# Set max attempts")
        code_lines.append(f"{indent}max_retry_attempts = {attempts_value}")
        code_lines.append(f"{indent}if not isinstance(max_retry_attempts, int) or max_retry_attempts < 1:")
        code_lines.append(f"{indent}    max_retry_attempts = 3  # Default to 3 attempts")
        
        # Process the backoff seconds input
        code_lines.append(f"{indent}# Set backoff seconds")
        code_lines.append(f"{indent}retry_backoff_seconds = {backoff_value}")
        code_lines.append(f"{indent}if not isinstance(retry_backoff_seconds, (int, float)) or retry_backoff_seconds < 0:")
        code_lines.append(f"{indent}    retry_backoff_seconds = 0  # Default to no backoff")
        
        # Generate the retry loop
        code_lines.append(f"{indent}# Execute retry loop")
        code_lines.append(f"{indent}for _retry_attempt in range(1, max_retry_attempts + 1):")
        code_lines.append(f"{indent}    {var_name}['attempts_made'] = _retry_attempt")
        code_lines.append(f"{indent}    try:")
        
        # Look up the step to retry dynamically
        if action_step_id in steps_by_id:
            step_to_retry = steps_by_id[action_step_id]
            retry_action = step_to_retry.get('action', '')
            retry_inputs = step_to_retry.get('inputs', {})
            
            if '.' in retry_action:
                integration, func = retry_action.split('.', 1)
                
                # Process inputs
                arg_list = []
                for input_name, input_val in retry_inputs.items():
                    val_ref = _process_reference(input_val, step_var, context_id=sid)
                    arg_list.append(f"{input_name}={val_ref}")
                
                args_str = ", ".join(arg_list)
                
                # Use module_var based on integration and action name
                if integration == 'variables':
                    module_var = 'variables_module'
                else:
                    # Default to the function name or first part before underscore
                    module_var = func.split('_')[0] if '_' in func else func
                
                # Directly generate the function call code
                code_lines.append(f"{indent}        {action_step_id}_result = {module_var}.{func}({args_str})")
                code_lines.append(f"{indent}        {var_name}['last_action_result'] = {action_step_id}_result")
                code_lines.append(f"{indent}        {var_name}['action_succeeded'] = True")
                code_lines.append(f"{indent}        break  # Success - exit retry loop")
        else:
            # Generic retry code if we don't know the step at generation time
            code_lines.append(f"{indent}        # Execute the action step dynamically")
            code_lines.append(f"{indent}        # This placeholder would be replaced with actual retry logic")
            code_lines.append(f"{indent}        {var_name}['last_action_result'] = None")
            code_lines.append(f"{indent}        {var_name}['action_succeeded'] = False")
            code_lines.append(f"{indent}        break")
        
        # Handle retry exception and backoff
        code_lines.append(f"{indent}    except Exception as e:")
        code_lines.append(f"{indent}        # Retry failed - handle error")
        code_lines.append(f"{indent}        {var_name}['last_exception'] = {{'type': type(e).__name__, 'message': str(e)}}")
        code_lines.append(f"{indent}        if _retry_attempt < max_retry_attempts:")
        code_lines.append(f"{indent}            # Not the last attempt - sleep before retrying")
        code_lines.append(f"{indent}            if retry_backoff_seconds > 0:")
        code_lines.append(f"{indent}                time.sleep(retry_backoff_seconds)")
        code_lines.append(f"{indent}        else:")
        code_lines.append(f"{indent}            # Last attempt failed - update result")
        code_lines.append(f"{indent}            {var_name}['action_succeeded'] = False")
    
    elif control_type == 'subflow':
        flow_id = inputs.get('flow_id', inputs.get('flow_ref', 'unknown_flow'))
        subflow_inputs = inputs.get('inputs', {})
        
        flow_id_value = _process_reference(flow_id, step_var, context_id=sid)
        
        code_lines.append(f"{indent}# Execute subflow for step {sid}")
        code_lines.append(f"{indent}from pathlib import Path")
        code_lines.append(f"{indent}# Prepare subflow inputs")
        code_lines.append(f"{indent}subflow_inputs = {{}}")
        
        # Process subflow inputs
        for input_name, input_val in subflow_inputs.items():
            input_val_str = _process_reference(input_val, step_var, context_id=sid)
            code_lines.append(f"{indent}subflow_inputs['{input_name}'] = {input_val_str}")
        
        # Add flow variables to inputs
        code_lines.append(f"{indent}# Pass current flow variables to subflow")
        code_lines.append(f"{indent}subflow_inputs.update(flow_variables)")
        
        # Run subflow
        code_lines.append(f"{indent}subflow_path = Path({flow_id_value})")
        code_lines.append(f"{indent}if not subflow_path.suffix:")
        code_lines.append(f"{indent}    subflow_path = subflow_path.with_suffix('.yaml')")
        code_lines.append(f"{indent}# This is a placeholder for actual subflow execution")
        code_lines.append(f"{indent}print(f\"Executing subflow: {{subflow_path}} with inputs: {{subflow_inputs}}\")")
        code_lines.append(f"{indent}{var_name} = {{")
        code_lines.append(f"{indent}    'subflow_id': {flow_id_value},")
        code_lines.append(f"{indent}    'result': {{'status': 'simulated'}},")
        code_lines.append(f"{indent}    'terminated_by_subflow': False")
        code_lines.append(f"{indent}}}")
    
    elif control_type == 'terminate':
        message = inputs.get('message', f"Flow terminated by step '{sid}'")
        message_value = _process_reference(message, step_var, context_id=sid)
        
        code_lines.append(f"{indent}# Terminate flow execution for step {sid}")
        code_lines.append(f"{indent}{var_name} = {{")
        code_lines.append(f"{indent}    'terminated': True,")
        code_lines.append(f"{indent}    'message': {message_value}")
        code_lines.append(f"{indent}}}")
        code_lines.append(f"{indent}print(f\"Flow terminated by step '{sid}': {{{{message}}}}\")")
        code_lines.append(f"{indent}# Note: In a real flow engine, execution would stop here")
    
    else:
        # For other control structures, use a function call approach
        code_lines.append(f"{indent}# Control: {control_type}")
        
        # Use the control module consistently
        module_var = "control"
        
        code_lines.append(f"{indent}{var_name} = {module_var}.{control_type}(")
        
        for i, (name, val) in enumerate(inputs.items()):
            formatted_val = _process_reference(val, step_var, context_id=sid)
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
    
    # --- NEW: remember every variable that can legitimately be read later ------------
    global flow_variable_names
    flow_variable_names.clear()  # Clear any previous values
    # any step that *creates* a flow‐variable
    for s in steps:
        if s.get("action") in ("variables.set_local", "variables.set", "variables.get_local", "variables.get"):
            name = s.get("inputs", {}).get("name")
            if name:
                flow_variable_names.add(name)
    # ------------------------------------------------------------------------------
    
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
                # PATCHED: Check if get_implementation_for_action is a function before calling it
                if hasattr(registry, 'get_implementation_for_action') and callable(registry.get_implementation_for_action):
                    try:
                        implementation = registry.get_implementation_for_action(action)
                    except Exception as e:
                        if use_native_control:
                            print(f"Warning: Error getting implementation for action {action}: {str(e)}")
                        implementation = None
                # PATCHED: Check if get_module_for_action is a function before calling it
                elif hasattr(registry, 'get_module_for_action') and callable(registry.get_module_for_action):
                    try:
                        _, module_name = registry.get_module_for_action(action)
                    except Exception as e:
                        if use_native_control:
                            print(f"Warning: Error getting module for action {action}: {str(e)}")
                        module_name = None
            
            # Try to parse implementation string if available
            if implementation and isinstance(implementation, str) and '.' in implementation:
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
                    default_val = _process_reference(default, step_var, context_id=None)
                    code_lines.append(f"{indent}{var_name} = {{'value': flow_variables.get({repr(var_key)}, {default_val})}}")
            
            elif func == 'set_local':
                var_key = inputs.get('name', '')
                value = _process_reference(inputs.get('value'), step_var, context_id=None)
                code_lines.append(f"{indent}flow_variables[{repr(var_key)}] = {value}")
                code_lines.append(f"{indent}{var_name} = {{'value': {value}}}")
            
            elif func == 'get_env':
                env_key = inputs.get('name', '')
                default = inputs.get('default')
                
                if default is None:
                    code_lines.append(f"{indent}{var_name} = {{'value': os.environ.get({repr(env_key)}, '')}}")
                else:
                    default_val = _process_reference(default, step_var, context_id=None)
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
                    default_val = _process_reference(default, step_var, context_id=None)
                    code_lines.append(f"{indent}# Get variable from flow_variables or environment with default")
                    code_lines.append(f"{indent}if {repr(var_key)} in flow_variables:")
                    code_lines.append(f"{indent}    {var_name} = {{'value': flow_variables.get({repr(var_key)})}}")
                    code_lines.append(f"{indent}else:")
                    code_lines.append(f"{indent}    {var_name} = {{'value': os.environ.get({repr(var_key)}, {default_val})}}")
            
            elif func == 'set':
                # Legacy set - always sets to flow variables
                var_key = inputs.get('name', '')
                value = _process_reference(inputs.get('value'), step_var, context_id=None)
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
                if implementation and isinstance(implementation, str) and '.' in implementation:
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
                    formatted_val = _process_reference(val, step_var, context_id=None)
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