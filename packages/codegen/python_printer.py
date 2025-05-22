

import os
from typing import Dict, List, Any, Optional, Set

# Assuming ir module is correctly placed relative to this file
# For testing, let's define dummy IR classes if not available.
try:
    from .ir import (
        IRFlow, IRStep, IRControlFlow, IRVariableRef,
        IRLiteral, IRTemplate, IRNodeType
    )
except ImportError:
    # Dummy classes for standalone testing
    class IRNodeType: pass
    class IRStep:
        def __init__(self, node_id, action, inputs=None, node_type=None):
            self.node_id = node_id
            self.action = action
            self.inputs = inputs or {}
            self.node_type = node_type
            # For the 'output_variable_name' logic if we were to add it for basic.add example
            # self.output_variable_name = None


    class IRControlFlow(IRStep):
        def __init__(self, node_id, action, control_type, inputs=None, branches=None, node_type=None):
            super().__init__(node_id, action, inputs, node_type)
            self.control_type = control_type
            self.branches = branches or {}

    class IRVariableRef:
        def __init__(self, source_type, source_name, field_path=None):
            self.source_type = source_type
            self.source_name = source_name
            self.field_path = field_path
        def __repr__(self):
            return f"IRVariableRef({self.source_type}, {self.source_name}, {self.field_path})"


    class IRLiteral:
        def __init__(self, node_id, value, value_type): # node_id often unused for pure literals in expressions
            self.node_id = node_id # but good to have for consistency if it's also a step input
            self.value = value
            self.value_type = value_type
        def __repr__(self):
            return f"IRLiteral({self.value!r}, {self.value_type})"

    class IRTemplate:
        def __init__(self, node_id, template_string, expressions):
            self.node_id = node_id # same as IRLiteral for node_id
            self.template = template_string
            self.expressions = expressions # List of IRVariableRef, IRLiteral etc.
        def __repr__(self):
            return f"IRTemplate({self.template!r}, {self.expressions})"

    class IRFlow:
        def __init__(self, flow_id, name, steps: List[IRStep]): # Added name for consistency, though not used in this snippet
            self.flow_id = flow_id
            self.name = name
            self.steps = steps
            self._step_map = {step.node_id: step for step in steps if step.node_id}
        def add_step(self, step: 'IRStep'): # Added for consistency with previous fix
            self.steps.append(step)
            if step.node_id:
                self._step_map[step.node_id] = step
        def get_step_by_id(self, step_id: str) -> Optional[IRStep]:
            return self._step_map.get(step_id)

class PythonPrinter:
    """Generates Python code from IR."""

    def __init__(self, use_native_control=True, integration_handler=None):
        self.use_native_control = use_native_control
        self.integration_handler = integration_handler
        self.module_imports: Dict[str, Set[str]] = {} # Kept for now, but new import logic less reliant
        self.flow_variable_names: Set[str] = set() 
        self.env_vars: Set[str] = set()
        self.step_var: Dict[str, str] = {}  

    def print_flow(self, flow: IRFlow) -> str:
        """Generate Python code for a flow."""
        self.module_imports = {}
        self.flow_variable_names = set()
        self.env_vars = set()
        self.step_var = {step.node_id: self._sanitize_name(step.node_id) for step in flow.steps}
        
        self._analyze_flow(flow)

        code_lines = [] # This will hold all lines of the generated file

        # --- IMPORT SECTION ---
        all_import_statements = set()

        # Core imports
        if any(s.action == "variables.get_env" or s.action == "variables.get" for s in flow.steps) or self.env_vars:
            all_import_statements.add("import os")
        if self.env_vars:
            all_import_statements.add("from dotenv import load_dotenv")

        # Integration handler imports
        if self.integration_handler:
            integrations_to_import_from_handler = set()
            for step_obj in flow.steps: 
                if "." in step_obj.action:
                    integration_name, _ = step_obj.action.split(".", 1)
                    
                    if integration_name == "control" and self.use_native_control:
                        continue # Native control, no import needed
                    if integration_name in ("variables", "basic"):
                        continue # Native/special handling, no import needed
                    integrations_to_import_from_handler.add(integration_name)

            for integration_name in sorted(list(integrations_to_import_from_handler)):
                statements = self.integration_handler.get_import_statements(integration_name, "python")
                for stmt in statements:
                    all_import_statements.add(stmt)
        
        # Add sorted unique import statements to code_lines
        if all_import_statements:
            code_lines.extend(sorted(list(all_import_statements)))
            code_lines.append("") # Add a blank line after all imports
        # --- END OF IMPORT SECTION ---

        code_lines.append(f"def run_flow():")
        indent = "    "

        if self.env_vars:
            code_lines.append(f"{indent}# Load environment variables from .env file")
            code_lines.append(f"{indent}load_dotenv()")
            code_lines.append("")
        
        for i, step in enumerate(flow.steps):
            step_code = self._generate_step_code(step, indent, flow)
            code_lines.extend(step_code)
            if i < len(flow.steps) -1 and step_code: # Add a blank line if not the last step's code and step_code wasn't empty
                code_lines.append("")

        # Remove last blank line if it exists from loop
        if code_lines and code_lines[-1] == "":
            code_lines.pop()

        if flow.steps:
            # Determine the variable name of the last step's result
            # Default to its sanitized ID if not found in step_var (should be rare)
            last_step_var_name = self.step_var.get(flow.steps[-1].node_id, self._sanitize_name(flow.steps[-1].node_id))
            code_lines.append(f"{indent}return {last_step_var_name}")
        else:
            code_lines.append(f"{indent}return None")

        return "\n".join(code_lines)

    def _sanitize_name(self, name: str) -> str:
        import re
        name = re.sub(r'\W|^(?=\d)', '_', name)
        if not name: return "_var" 
        return name


    def _analyze_flow(self, flow: IRFlow):
        for step in flow.steps:
            if step.action in ("variables.set_local", "variables.set"):
                if "name" in step.inputs:
                    name_node = step.inputs["name"]
                    if isinstance(name_node, IRLiteral) and isinstance(name_node.value, str):
                        actual_var_name = self._sanitize_name(name_node.value)
                        self.step_var[step.node_id] = actual_var_name
                        self.flow_variable_names.add(actual_var_name)
            
            if step.action == "variables.get_env": 
                if "name" in step.inputs and isinstance(step.inputs["name"], IRLiteral):
                    self.env_vars.add(step.inputs["name"].value)

            # self.module_imports is not actively populated by this version of _analyze_flow
            # as import generation relies more on integration_handler directly.
            # If step.action.startswith("some_integration.") and not handled by integration_handler:
            #    self.module_imports.setdefault("integrations.some_integration", set()).add("specific_func")

            for input_node in step.inputs.values():
                self._analyze_variable_references(input_node)

    def _analyze_variable_references(self, node: Any):
        if isinstance(node, IRVariableRef):
            if node.source_type == "env":
                if node.source_name: self.env_vars.add(node.source_name) # Ensure source_name is not None
            elif node.source_type == "flow_var": 
                if node.source_name: self.flow_variable_names.add(self._sanitize_name(node.source_name))
        elif isinstance(node, IRTemplate):
            for expr in node.expressions:
                self._analyze_variable_references(expr)
    
    def _get_actual_variable_name(self, name_node: Any) -> str:
        if isinstance(name_node, IRLiteral) and isinstance(name_node.value, str):
            return self._sanitize_name(name_node.value)
        if isinstance(name_node, IRVariableRef) and name_node.source_type == "flow_var":
             return self._sanitize_name(name_node.source_name)

        # Fallback if name_node is an expression that needs to be evaluated to a string
        # This is a simplified approach; robustly handling this would require type checking or assumptions.
        # For now, we assume it's a direct string or simple reference.
        # If it's another type of IRNode, generating its expression might be needed, but could be complex.
        # For this example, let's assume it evaluates to a string or a variable holding a string.
        if isinstance(name_node, IRVariableRef): # e.g., step output or env var holding a name
            # This path implies _generate_expression should be used, but that's for values, not names.
            # Sticking to literal or flow_var ref for names.
            pass

        # If name_node is an IRTemplate, it means the variable name itself is dynamic.
        # This is a very advanced case. For now, we will raise an error or use a placeholder.
        # For example, if name_node is "my_var_{{idx}}".
        # The _generate_expression for the template would produce an f-string.
        # Using eval(fstring) is unsafe. This would need careful design.
        # print(f"Warning: Dynamic variable name from template for 'set' operation is complex: {name_node}")
        # return f"dynamic_var_placeholder_{name_node.node_id if hasattr(name_node, 'node_id') else 'unknown'}"

        raise ValueError(f"Variable name for 'set' operation must be a string literal or simple flow_var ref, got {type(name_node)}")


    def _generate_step_code(self, step: IRStep, indent: str, flow: IRFlow) -> List[str]:
        code_lines = []
        step_id = step.node_id
        var_name = self.step_var[step_id] 
        
        code_lines.append(f"{indent}# Step: {self._sanitize_name(step_id)} ({step.action})")

        if isinstance(step, IRControlFlow) and self.use_native_control:
            control_type = step.control_type
            py_control_var_name = self._sanitize_name(var_name) 

            if control_type in ("if_node", "if"):
                condition = step.inputs.get("condition")
                condition_expr = self._generate_expression(condition, indent, flow)
                
                code_lines.append(f"{indent}if {condition_expr}:")
                if step.branches.get("then"):
                    for then_step in step.branches["then"]:
                        then_code = self._generate_step_code(then_step, indent + "    ", flow)
                        code_lines.extend(then_code)
                else: # Ensure at least one line in 'then' if branch is empty
                    code_lines.append(f"{indent}    pass")
                code_lines.append(f"{indent}    {py_control_var_name} = {{'result': True}}") # Assign result after branch
                
                if step.branches.get("else"):
                    code_lines.append(f"{indent}else:")
                    for else_step in step.branches["else"]:
                        else_code = self._generate_step_code(else_step, indent + "    ", flow)
                        code_lines.extend(else_code)
                    code_lines.append(f"{indent}    {py_control_var_name} = {{'result': False}}")
                else:
                    code_lines.append(f"{indent}else:") 
                    code_lines.append(f"{indent}    pass") # Ensure at least one line in 'else' if branch is empty
                    code_lines.append(f"{indent}    {py_control_var_name} = {{'result': False}}")

            elif control_type == "switch":
                value_expr = self._generate_expression(step.inputs.get("value"), indent, flow)
                switch_val_var = f"switch_value_{self._sanitize_name(step_id)}" # Unique name for switch value
                code_lines.append(f"{indent}{switch_val_var} = {value_expr}")
                code_lines.append(f"{indent}{py_control_var_name} = {{'matched_case': None}}")

                first_case = True
                has_matching_branch_run = False # To track if any case/default branch code was generated

                for case_name_key, case_steps_list in step.branches.items():
                    if case_name_key == "default": continue

                    if case_name_key.startswith("case_"):
                        # Assuming case value is string after "case_"
                        # For non-string case values, IRBuilder needs to store type or use a richer structure
                        case_val_str = case_name_key[5:]
                        # Attempt to infer type for repr, default to string
                        try:
                            case_val_actual = int(case_val_str)
                        except ValueError:
                            try:
                                case_val_actual = float(case_val_str)
                            except ValueError:
                                if case_val_str.lower() == "true": case_val_actual = True
                                elif case_val_str.lower() == "false": case_val_actual = False
                                else: case_val_actual = case_val_str # string
                        
                        case_val_repr = repr(case_val_actual)
                        
                        keyword = "if" if first_case else "elif"
                        code_lines.append(f"{indent}{keyword} {switch_val_var} == {case_val_repr}:")
                        first_case = False
                        
                        code_lines.append(f"{indent}    {py_control_var_name}['matched_case'] = {case_val_repr}")
                        if case_steps_list:
                            for case_step in case_steps_list:
                                case_code = self._generate_step_code(case_step, indent + "    ", flow)
                                code_lines.extend(case_code)
                            has_matching_branch_run = True
                        else:
                            code_lines.append(f"{indent}    pass")
                
                if "default" in step.branches:
                    keyword = "else" if first_case else "else:" # if only default, it's `if False: pass \n else: ...`
                    if first_case: # No cases, only default
                         code_lines.append(f"{indent}# No cases defined, running default directly")
                    else: # Cases existed
                         code_lines.append(f"{indent}else:")
                    
                    code_lines.append(f"{indent}    {py_control_var_name}['matched_case'] = 'default'")
                    if step.branches["default"]:
                        for default_step_obj in step.branches["default"]:
                            default_code = self._generate_step_code(default_step_obj, indent + "    ", flow)
                            code_lines.extend(default_code)
                        has_matching_branch_run = True
                    else:
                        code_lines.append(f"{indent}    pass")
                
                if not has_matching_branch_run and first_case: # No cases and no default ran
                    code_lines.append(f"{indent}# No cases matched and no default branch")
                    code_lines.append(f"{indent}pass")


            elif control_type in ("while_loop", "while"):
                condition_input = step.inputs.get("condition")
                max_iterations_node = step.inputs.get("max_iterations", IRLiteral("", 100, "int")) 
                max_iter_expr = self._generate_expression(max_iterations_node, indent, flow)
                
                iter_count_var = f"iteration_count_{self._sanitize_name(step_id)}"
                
                code_lines.append(f"{indent}{iter_count_var} = 0")
                
                # Condition must be re-evaluated each time, so we generate it inside the loop logic as well
                # For the `while` statement, generate the expression directly
                condition_code_for_while = self._generate_expression(condition_input, indent, flow)
                code_lines.append(f"{indent}while ({condition_code_for_while}) and {iter_count_var} < {max_iter_expr}:")
                code_lines.append(f"{indent}    {iter_count_var} += 1")
                
                body_steps = step.branches.get("body", [])
                if body_steps:
                    for body_step in body_steps:
                        body_code = self._generate_step_code(body_step, indent + "    ", flow)
                        code_lines.extend(body_code)
                else:
                    code_lines.append(f"{indent}    pass # Empty loop body")
                
                # Re-evaluate condition for the loop_ended_naturally flag
                # This is tricky if condition has side effects. Assuming it's mostly referential.
                condition_code_for_result = self._generate_expression(condition_input, indent, flow)
                code_lines.append(f"{indent}{py_control_var_name} = {{")
                code_lines.append(f"{indent}    'iterations_run': {iter_count_var},")
                code_lines.append(f"{indent}    'loop_ended_naturally': not ({condition_code_for_result}) if {iter_count_var} < {max_iter_expr} else False")
                code_lines.append(f"{indent}}}")

            elif control_type == "for_each":
                list_input = step.inputs.get("list", IRLiteral("", [], "list"))
                list_expr = self._generate_expression(list_input, indent, flow)
                iterator_name_node = step.inputs.get("iterator_name", IRLiteral("", "item", "str"))
                actual_iterator_name = self._get_actual_variable_name(iterator_name_node) 
                iterator_index_var = f"{actual_iterator_name}_index" 

                iter_count_var = f"iteration_count_{self._sanitize_name(step_id)}"
                
                code_lines.append(f"{indent}{iter_count_var} = 0")
                for_each_list_var = f"for_each_list_{self._sanitize_name(step_id)}"
                code_lines.append(f"{indent}{for_each_list_var} = {list_expr}")
                
                code_lines.append(f"{indent}for {iterator_index_var}, {actual_iterator_name} in enumerate({for_each_list_var}):")
                code_lines.append(f"{indent}    {iter_count_var} += 1")

                body_steps = step.branches.get("body", [])
                if body_steps:
                    for body_step in body_steps:
                        body_code = self._generate_step_code(body_step, indent + "    ", flow)
                        code_lines.extend(body_code)
                else:
                    code_lines.append(f"{indent}    pass # Empty loop body")
                
                code_lines.append(f"{indent}{py_control_var_name} = {{")
                code_lines.append(f"{indent}    'iterations_completed': {iter_count_var},")
                code_lines.append(f"{indent}}}")
            
            elif control_type in ("try_catch", "try"):
                code_lines.append(f"{indent}try:")
                try_steps = step.branches.get("try", [])
                if try_steps:
                    for try_step in try_steps:
                        try_code = self._generate_step_code(try_step, indent + "    ", flow)
                        code_lines.extend(try_code)
                else:
                    code_lines.append(f"{indent}    pass # Empty try block")

                code_lines.append(f"{indent}    {py_control_var_name} = {{'success': True, 'error_details': None}}")
                code_lines.append(f"{indent}except Exception as e:")
                code_lines.append(f"{indent}    {py_control_var_name} = {{")
                code_lines.append(f"{indent}        'success': False,")
                code_lines.append(f"{indent}        'error_details': {{'type': type(e).__name__, 'message': str(e)}}")
                code_lines.append(f"{indent}    }}")
                
                # Make error details available to catch block steps if needed (e.g., as a flow_var)
                # For simplicity, we assume catch block steps might refer to common error vars if design supports it
                # or the py_control_var_name itself.

                catch_steps = step.branches.get("catch", [])
                if catch_steps:
                    for catch_step in catch_steps:
                        catch_code = self._generate_step_code(catch_step, indent + "    ", flow)
                        code_lines.extend(catch_code)
                else: # No explicit catch branch, error is caught and reported in py_control_var_name
                    pass
        
        elif step.action.startswith("variables."):
            py_var_name_for_output = self._sanitize_name(var_name) 

            if step.action in ("variables.set_local", "variables.set"):
                name_node = step.inputs["name"]
                actual_target_var_name = py_var_name_for_output # From self.step_var logic
                
                value_expr = self._generate_expression(step.inputs.get("value"), indent, flow)
                code_lines.append(f"{indent}{actual_target_var_name} = {value_expr}")
                # self.step_var[step.node_id] already points to actual_target_var_name

            elif step.action in ("variables.get_local", "variables.get"):
                name_node = step.inputs["name"] 
                source_var_to_get_str_name = self._get_actual_variable_name(name_node) 
                
                default_node = step.inputs.get("default")
                default_expr = self._generate_expression(default_node, indent, flow) if default_node else "None"
                
                if step.action == "variables.get_local":
                    code_lines.append(f"{indent}try:")
                    code_lines.append(f"{indent}    {py_var_name_for_output} = {source_var_to_get_str_name}")
                    code_lines.append(f"{indent}except NameError:")
                    code_lines.append(f"{indent}    {py_var_name_for_output} = {default_expr}")
                
                elif step.action == "variables.get": 
                    code_lines.append(f"{indent}try:")
                    code_lines.append(f"{indent}    {py_var_name_for_output} = {source_var_to_get_str_name}")
                    code_lines.append(f"{indent}except NameError:")
                    code_lines.append(f"{indent}    {py_var_name_for_output} = os.environ.get({repr(source_var_to_get_str_name)}, {default_expr})")

            elif step.action == "variables.get_env":
                name_node = step.inputs.get("name") # This should be an IRLiteral with the env var key as string
                if isinstance(name_node, IRLiteral) and isinstance(name_node.value, str):
                    env_var_key_repr = repr(name_node.value)
                else: # If name is dynamic (e.g., from another var)
                    env_var_key_expr = self._generate_expression(name_node, indent, flow)
                    # This path implies name_expr could be f"var_holding_key_name"
                    # os.environ.get expects a string literal or variable holding string for key.
                    # For simplicity, we'll assume name_expr evaluates to a string key.
                    env_var_key_repr = env_var_key_expr


                default_expr = self._generate_expression(step.inputs.get("default"), indent, flow)
                code_lines.append(f"{indent}{py_var_name_for_output} = os.environ.get({env_var_key_repr}, {default_expr})")
        
        elif step.action.startswith("basic."):
            op_map = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}
            action_name = step.action.split(".")[1]
            py_var_name_for_output = self._sanitize_name(var_name)

            if action_name in op_map:
                # Determine parameter names based on action, default to 'a'/'b' or 'x'/'y'
                if action_name == "add": lhs_param_name, rhs_param_name = "a", "b"
                elif action_name == "subtract": lhs_param_name, rhs_param_name = "x", "y"
                elif action_name == "multiply": lhs_param_name, rhs_param_name = "x", "y"
                elif action_name == "divide": lhs_param_name, rhs_param_name = "x", "y"
                else: lhs_param_name, rhs_param_name = "operand1", "operand2" # Fallback, should match manifest

                # Check if these specific param names are in inputs, otherwise use generic if possible
                # This part depends on how IRBuilder maps basic action inputs. Assume they are consistent.
                lhs_val_node = step.inputs.get(lhs_param_name, step.inputs.get(list(step.inputs.keys())[0] if step.inputs else None))
                rhs_val_node = step.inputs.get(rhs_param_name, step.inputs.get(list(step.inputs.keys())[1] if len(step.inputs)>1 else None))


                lhs = self._generate_expression(lhs_val_node, indent, flow)
                rhs = self._generate_expression(rhs_val_node, indent, flow)
                op_symbol = op_map[action_name]
                code_lines.append(f"{indent}{py_var_name_for_output} = {lhs} {op_symbol} {rhs}")
            else:
                code_lines.append(f"{indent}# Unsupported basic action: {step.action}")
                code_lines.append(f"{indent}{py_var_name_for_output} = None")
        
        else: 
            py_var_name_for_output = self._sanitize_name(var_name)
            if "." in step.action:
                integration, action_name_str = step.action.split(".", 1)
                
                # Default module/function naming convention
                module_var_py = self._sanitize_name(integration) 
                func_name_py = self._sanitize_name(action_name_str)

                if self.integration_handler:
                    call_str_template = self.integration_handler.get_function_call(
                        integration, action_name_str, "python")
                    if call_str_template:
                        if "." in call_str_template:
                             mod_part, func_part = call_str_template.split(".", 1)
                             module_var_py = self._sanitize_name(mod_part) # Potentially reassigns
                             func_name_py = self._sanitize_name(func_part)
                        else: # Direct function call, no module prefix
                            module_var_py = None 
                            func_name_py = self._sanitize_name(call_str_template)
                
                arg_list = []
                for input_name, input_node in step.inputs.items():
                    input_expr = self._generate_expression(input_node, indent, flow)
                    arg_list.append(f"{self._sanitize_name(input_name)}={input_expr}")
                
                args_str = ", ".join(arg_list)
                if module_var_py: # e.g. my_integration_module.my_action_func(...)
                    code_lines.append(f"{indent}{py_var_name_for_output} = {module_var_py}.{func_name_py}({args_str})")
                else: # e.g. my_direct_action_func(...)
                    code_lines.append(f"{indent}{py_var_name_for_output} = {func_name_py}({args_str})")
            else: # Action without a "." separator (e.g. a custom global function)
                # This case might imply a direct function call if printer supports it.
                # For now, treat as unknown.
                func_name_py = self._sanitize_name(step.action)
                arg_list = [self._generate_expression(val_node, indent, flow) for val_node in step.inputs.values()]
                args_str = ", ".join(arg_list) # Positional arguments if names are not critical
                code_lines.append(f"{indent}# Unknown action format or direct function call: {step.action}")
                code_lines.append(f"{indent}{py_var_name_for_output} = {func_name_py}({args_str}) # Assuming positional args")
        
        return code_lines

    def _generate_expression(self, node: Any, indent: str, flow: IRFlow) -> str:
        if node is None:
            return "None"
            
        if isinstance(node, IRLiteral):
            if node.value_type == "expression": 
                return str(node.value) # Raw expression, use as-is
            else: # For other literal types, repr() handles Python syntax correctly
                return repr(node.value)
                
        elif isinstance(node, IRVariableRef):
            source_name_sanitized = self._sanitize_name(node.source_name)
            if node.source_type == "env":
                # node.source_name is the actual environment variable key (string)
                return f"os.environ.get({repr(node.source_name)}, None)" 
                
            elif node.source_type == "flow_var":
                return source_name_sanitized # This is a direct Python variable name
                
            elif node.source_type == "step":
                # node.source_name is the step_id of the referenced step
                # step_py_var_name is the Python variable holding that step's result
                step_py_var_name = self.step_var.get(node.source_name, source_name_sanitized) # Fallback to sanitized id

                referenced_step = flow.get_step_by_id(node.source_name)
                is_direct_value_type = False # Does the step_py_var_name directly hold the value?
                if referenced_step:
                    action = referenced_step.action
                    # For these actions, the python variable assigned (e.g. result_of_get_env)
                    # IS the value, not a dict like {'value': ...}
                    if action.startswith("variables.set") or \
                       action.startswith("variables.get") or \
                       action.startswith("variables.get_env") or \
                       action.startswith("basic."):
                       is_direct_value_type = True
                
                if is_direct_value_type:
                    # If step_py_var_name is already the direct value, field_path (e.g. '.value') is not used.
                    return step_py_var_name
                else: # For dict-producing steps (control flow, complex integrations that return dicts)
                    if node.field_path:
                        # field_path should be the key in the dictionary result of the step
                        return f"{step_py_var_name}['{node.field_path}']" # Assume field_path is a valid key string
                    else: # No field path, reference to the whole result (likely a dict)
                        return step_py_var_name 
                    
        elif isinstance(node, IRTemplate):
            f_string_content = node.template
            
            # Regex to find placeholders like {{...}} or {...}
            # This simple replacement assumes placeholders don't contain literal "}" or "{{" themselves.
            # More robust parsing might be needed for complex templates.
            
            # Process expressions and create replacement map
            # Need to handle different placeholder syntaxes like {{var.name}}, {{step_id.output}}, {{env.VAR}}
            # The IRTemplate.expressions list contains IRNodes for each placeholder.
            
            # Sort expressions by a heuristic of their placeholder length to avoid partial replacements
            # e.g. replace "{{step.output.long}}" before "{{step.output}}" if both were somehow expressions.
            # This is complex to get perfect without full template parsing.
            # A common way is to replace with unique temporary placeholders first.
            
            processed_expressions = []
            for i, expr_node_in_template in enumerate(node.expressions):
                py_expr_for_template = self._generate_expression(expr_node_in_template, indent, flow)
                
                # Try to find the original placeholder string for this expression in the template
                # This is heuristic. IRTemplate ideally would store original placeholder string for each expression.
                original_placeholder_found = False
                if isinstance(expr_node_in_template, IRVariableRef):
                    ref_src_type = expr_node_in_template.source_type
                    ref_src_name = expr_node_in_template.source_name # Not sanitized, for matching template
                    ref_field = expr_node_in_template.field_path

                    possible_placeholders = []
                    if ref_src_type == "flow_var":
                        possible_placeholders.append(f"{{{{var.{ref_src_name}}}}}")
                        possible_placeholders.append(f"{{{{local.{ref_src_name}}}}}")
                    elif ref_src_type == "env":
                        possible_placeholders.append(f"{{{{env.{ref_src_name}}}}}")
                    elif ref_src_type == "step":
                        if ref_field:
                            possible_placeholders.append(f"{{{{{ref_src_name}.{ref_field}}}}}")
                        else: # Referencing whole step output (less common in templates)
                            possible_placeholders.append(f"{{{{{ref_src_name}}}}}")
                    
                    # Also check for single-brace versions if template uses them
                    single_brace_placeholders = [ph.replace("{{", "{").replace("}}", "}") for ph in possible_placeholders]
                    possible_placeholders.extend(single_brace_placeholders)
                    
                    for ph_to_replace in possible_placeholders:
                        if ph_to_replace in f_string_content:
                            f_string_content = f_string_content.replace(ph_to_replace, f"{{{py_expr_for_template}}}")
                            original_placeholder_found = True
                            break # Found and replaced for this expression
                
                if not original_placeholder_found:
                    # Fallback: If original placeholder cannot be reliably determined,
                    # this indicates a mismatch or a very complex template structure not fully supported by this simple replacement.
                    # Or, the expression in IRTemplate is a literal/raw expression itself.
                    # If expr_node_in_template is an IRLiteral of type "expression", its value is part of the template
                    # and was expected to be replaced by py_expr_for_template.
                    # This path might be hit if node.expressions contains items that are not simple refs.
                    # For now, we'll assume simple {{ref}} replacement covers most cases.
                    # A robust solution would involve parsing node.template with knowledge of expression boundaries.
                    pass


            # Escape any literal braces for Python's f-string syntax
            # (e.g. user's "Show {{value}}" should become f"Show {{{py_expr_for_value}}}")
            # The replacement above already puts Python expressions inside {}.
            # Any remaining {{ or }} are literal.
            f_string_content = f_string_content.replace("{{", "{{").replace("}}", "}}") # For user's literal {{ or }}
            
            # If the template string might contain newlines, use triple-quoted f-string
            return f'f"""{f_string_content}"""' if '\n' in f_string_content else f'f"{f_string_content}"'
        
        # Fallback for unknown node types
        return repr(str(node))
