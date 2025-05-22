"""Enhanced Python code generator from IR with comprehensive import handling."""

import os
import re
from typing import Dict, List, Any, Optional, Set

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

    class IRLiteral:
        def __init__(self, node_id, value, value_type):
            self.node_id = node_id
            self.value = value
            self.value_type = value_type

    class IRTemplate:
        def __init__(self, node_id, template_string, expressions):
            self.node_id = node_id
            self.template = template_string
            self.expressions = expressions

    class IRFlow:
        def __init__(self, flow_id, name=None, steps=None):
            self.flow_id = flow_id
            self.name = name
            self.steps = steps or []
            self._step_map = {step.node_id: step for step in self.steps if step.node_id}
        
        def get_step_by_id(self, step_id: str) -> Optional[IRStep]:
            return self._step_map.get(step_id)

class PythonPrinter:
    """Enhanced Python code generator from IR with comprehensive import and dependency handling."""

    def __init__(self, use_native_control=True, integration_handler=None):
        self.use_native_control = use_native_control
        self.integration_handler = integration_handler
        self.flow_variable_names: Set[str] = set() 
        self.env_vars: Set[str] = set()
        self.step_var: Dict[str, str] = {}
        self.used_integrations: Set[str] = set()
        self.required_imports: Set[str] = set()

    def print_flow(self, flow: IRFlow) -> str:
        """Generate Python code for a flow with comprehensive import handling."""
        # Reset state
        self.flow_variable_names = set()
        self.env_vars = set()
        self.step_var = {step.node_id: self._sanitize_name(step.node_id) for step in flow.steps}
        self.used_integrations = set()
        self.required_imports = set()
        
        # Analyze flow to collect requirements
        self._analyze_flow(flow)

        code_lines = []

        # Generate imports section
        all_imports = self._generate_all_imports(flow)
        if all_imports:
            code_lines.extend(sorted(all_imports))
            code_lines.append("")

        # Generate main function
        code_lines.append("def run_flow():")
        indent = "    "

        # Add environment variable loading if needed
        if self.env_vars:
            code_lines.append(f"{indent}# Load environment variables from .env file")
            code_lines.append(f"{indent}try:")
            code_lines.append(f"{indent}    from dotenv import load_dotenv")
            code_lines.append(f"{indent}    load_dotenv()")
            code_lines.append(f"{indent}except ImportError:")
            code_lines.append(f"{indent}    pass  # dotenv not available")
            code_lines.append("")
        
        # Generate step code
        for i, step in enumerate(flow.steps):
            step_code = self._generate_step_code(step, indent, flow)
            code_lines.extend(step_code)
            if i < len(flow.steps) - 1 and step_code:
                code_lines.append("")

        # Return result
        if flow.steps:
            last_step_var_name = self.step_var.get(flow.steps[-1].node_id, self._sanitize_name(flow.steps[-1].node_id))
            code_lines.append(f"{indent}return {last_step_var_name}")
        else:
            code_lines.append(f"{indent}return None")

        return "\n".join(code_lines)

    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name to be a valid Python identifier."""
        name = re.sub(r'\W|^(?=\d)', '_', name)
        if not name: 
            return "_var"
        # Avoid Python keywords
        python_keywords = {
            'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
            'exec', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'not',
            'or', 'pass', 'print', 'raise', 'return', 'try', 'while', 'with', 'yield'
        }
        if name in python_keywords:
            name += "_var"
        return name

    def _analyze_flow(self, flow: IRFlow):
        """Analyze flow to collect required imports and dependencies."""
        for step in flow.steps:
            # Track variable operations
            if step.action in ("variables.set_local", "variables.set"):
                if "name" in step.inputs:
                    name_node = step.inputs["name"]
                    if isinstance(name_node, IRLiteral) and isinstance(name_node.value, str):
                        actual_var_name = self._sanitize_name(name_node.value)
                        self.step_var[step.node_id] = actual_var_name
                        self.flow_variable_names.add(actual_var_name)
            
            # Track environment variable usage
            if step.action == "variables.get_env": 
                if "name" in step.inputs and isinstance(step.inputs["name"], IRLiteral):
                    self.env_vars.add(step.inputs["name"].value)

            # Track integration usage
            if "." in step.action:
                integration_name = step.action.split(".", 1)[0]
                if integration_name not in ("variables", "basic", "control"):
                    self.used_integrations.add(integration_name)

            # Analyze variable references in inputs
            for input_node in step.inputs.values():
                self._analyze_variable_references(input_node)

    def _analyze_variable_references(self, node: Any):
        """Analyze variable references to collect environment variables."""
        if isinstance(node, IRVariableRef):
            if node.source_type == "env" and node.source_name:
                self.env_vars.add(node.source_name)
            elif node.source_type == "flow_var" and node.source_name: 
                self.flow_variable_names.add(self._sanitize_name(node.source_name))
        elif isinstance(node, IRTemplate):
            for expr in node.expressions:
                self._analyze_variable_references(expr)

    def _generate_all_imports(self, flow: IRFlow) -> Set[str]:
        """Generate all necessary import statements with multiple fallback strategies."""
        imports = set()
        
        # Core imports based on usage
        if self._uses_os_environ(flow) or self.env_vars:
            imports.add("import os")
        
        if self.env_vars:
            # Don't add dotenv import here as it's handled with try/except in the function
            pass
        
        # Integration imports with comprehensive fallback strategies
        for integration in self.used_integrations:
            integration_imports = self._get_integration_imports(integration)
            imports.update(integration_imports)
        
        # Add any additional required imports
        imports.update(self.required_imports)
        
        return imports

    def _uses_os_environ(self, flow: IRFlow) -> bool:
        """Check if flow uses os.environ directly."""
        for step in flow.steps:
            if step.action == "variables.get_env":
                return True
            # Check for env variable references in templates
            for input_node in step.inputs.values():
                if self._has_env_reference(input_node):
                    return True
        return False

    def _has_env_reference(self, node: Any) -> bool:
        """Check if a node has environment variable references."""
        if isinstance(node, IRVariableRef):
            return node.source_type == "env"
        elif isinstance(node, IRTemplate):
            return any(self._has_env_reference(expr) for expr in node.expressions)
        return False

    def _get_integration_imports(self, integration_name: str) -> Set[str]:
        """Get imports for an integration with multiple fallback strategies."""
        imports = set()
        
        # Strategy 1: Use integration handler
        if self.integration_handler:
            handler_imports = self.integration_handler.get_import_statements(integration_name, "python")
            if handler_imports:
                return set(handler_imports)
        
        # Strategy 2: Use standard patterns for common integrations
        standard_imports = self._get_standard_integration_imports(integration_name)
        if standard_imports:
            imports.update(standard_imports)
        
        # Strategy 3: Default integration import pattern
        if not imports:
            imports.add(f"from integrations.{integration_name} import *")
        
        return imports

    def _get_standard_integration_imports(self, integration_name: str) -> Set[str]:
        """Standard import patterns for common integrations."""
        patterns = {
            # HTTP/API integrations
            'http': {'import requests'},
            'https': {'import requests'},
            'api': {'import requests'},
            'rest': {'import requests'},
            'graphql': {'import requests'},
            
            # File system integrations
            'file': {'import os', 'import json'},
            'fs': {'import os', 'import json'},
            'csv': {'import csv'},
            'json': {'import json'},
            'xml': {'import xml.etree.ElementTree as ET'},
            
            # Database integrations
            'database': {'import sqlite3'},
            'db': {'import sqlite3'},
            'sqlite': {'import sqlite3'},
            'mysql': {'import mysql.connector'},
            'postgresql': {'import psycopg2'},
            'mongodb': {'import pymongo'},
            'redis': {'import redis'},
            
            # Email integrations
            'email': {'import smtplib', 'from email.mime.text import MIMEText'},
            'smtp': {'import smtplib', 'from email.mime.text import MIMEText'},
            'mail': {'import smtplib', 'from email.mime.text import MIMEText'},
            
            # Cloud integrations
            'aws': {'import boto3'},
            'azure': {'import azure.identity', 'import azure.storage.blob'},
            'gcp': {'import google.cloud'},
            
            # Social/Communication integrations
            'slack': {'import slack_sdk'},
            'discord': {'import discord'},
            'telegram': {'import telegram'},
            'twitter': {'import tweepy'},
            
            # Development integrations
            'github': {'import github'},
            'gitlab': {'import gitlab'},
            'jira': {'import jira'},
            
            # Data processing integrations
            'pandas': {'import pandas as pd'},
            'numpy': {'import numpy as np'},
            'excel': {'import openpyxl', 'import pandas as pd'},
            
            # System integrations
            'system': {'import subprocess', 'import os'},
            'shell': {'import subprocess'},
            'docker': {'import docker'},
            'kubernetes': {'import kubernetes'},
            
            # Utility integrations
            'datetime': {'import datetime'},
            'time': {'import time'},
            'uuid': {'import uuid'},
            'random': {'import random'},
        }
        
        return patterns.get(integration_name, set())

    def _get_actual_variable_name(self, name_node: Any) -> str:
        """Get the actual variable name from a name node."""
        if isinstance(name_node, IRLiteral) and isinstance(name_node.value, str):
            return self._sanitize_name(name_node.value)
        elif isinstance(name_node, IRVariableRef) and name_node.source_type == "flow_var":
            return self._sanitize_name(name_node.source_name)
        else:
            raise ValueError(f"Variable name for operation must be a string literal or simple flow_var ref, got {type(name_node)}")

    def _generate_step_code(self, step: IRStep, indent: str, flow: IRFlow) -> List[str]:
        """Generate Python code for a single step."""
        code_lines = []
        step_id = step.node_id
        var_name = self.step_var[step_id] 
        
        code_lines.append(f"{indent}# Step: {step_id} ({step.action})")

        if isinstance(step, IRControlFlow) and self.use_native_control:
            code_lines.extend(self._generate_control_flow_code(step, indent, flow))
        elif step.action.startswith("variables."):
            code_lines.extend(self._generate_variable_operation_code(step, indent, flow))
        elif step.action.startswith("basic."):
            code_lines.extend(self._generate_basic_operation_code(step, indent, flow))
        else:
            code_lines.extend(self._generate_integration_call_code(step, indent, flow))
        
        return code_lines

    def _generate_control_flow_code(self, step: IRControlFlow, indent: str, flow: IRFlow) -> List[str]:
        """Generate native Python control flow code."""
        code_lines = []
        control_type = step.control_type
        py_control_var_name = self._sanitize_name(self.step_var[step.node_id])

        if control_type in ("if_node", "if"):
            condition = step.inputs.get("condition")
            condition_expr = self._generate_expression(condition, indent, flow)
            
            code_lines.append(f"{indent}if {condition_expr}:")
            
            # Then branch
            if step.branches.get("then"):
                for then_step in step.branches["then"]:
                    then_code = self._generate_step_code(then_step, indent + "    ", flow)
                    code_lines.extend(then_code)
            else:
                code_lines.append(f"{indent}    pass")
            code_lines.append(f"{indent}    {py_control_var_name} = {{'result': True}}")
            
            # Else branch
            if step.branches.get("else"):
                code_lines.append(f"{indent}else:")
                for else_step in step.branches["else"]:
                    else_code = self._generate_step_code(else_step, indent + "    ", flow)
                    code_lines.extend(else_code)
                code_lines.append(f"{indent}    {py_control_var_name} = {{'result': False}}")
            else:
                code_lines.append(f"{indent}else:")
                code_lines.append(f"{indent}    pass")
                code_lines.append(f"{indent}    {py_control_var_name} = {{'result': False}}")

        elif control_type == "switch":
            value_expr = self._generate_expression(step.inputs.get("value"), indent, flow)
            switch_val_var = f"switch_value_{self._sanitize_name(step.node_id)}"
            code_lines.append(f"{indent}{switch_val_var} = {value_expr}")
            code_lines.append(f"{indent}{py_control_var_name} = {{'matched_case': None}}")

            first_case = True
            for case_name_key, case_steps_list in step.branches.items():
                if case_name_key == "default":
                    continue

                if case_name_key.startswith("case_"):
                    case_val_str = case_name_key[5:]
                    case_val_actual = self._parse_case_value(case_val_str)
                    case_val_repr = repr(case_val_actual)
                    
                    keyword = "if" if first_case else "elif"
                    code_lines.append(f"{indent}{keyword} {switch_val_var} == {case_val_repr}:")
                    first_case = False
                    
                    code_lines.append(f"{indent}    {py_control_var_name}['matched_case'] = {case_val_repr}")
                    if case_steps_list:
                        for case_step in case_steps_list:
                            case_code = self._generate_step_code(case_step, indent + "    ", flow)
                            code_lines.extend(case_code)
                    else:
                        code_lines.append(f"{indent}    pass")
            
            # Default case
            if "default" in step.branches:
                code_lines.append(f"{indent}else:")
                code_lines.append(f"{indent}    {py_control_var_name}['matched_case'] = 'default'")
                if step.branches["default"]:
                    for default_step_obj in step.branches["default"]:
                        default_code = self._generate_step_code(default_step_obj, indent + "    ", flow)
                        code_lines.extend(default_code)
                else:
                    code_lines.append(f"{indent}    pass")

        elif control_type in ("while_loop", "while"):
            condition_input = step.inputs.get("condition")
            max_iterations_node = step.inputs.get("max_iterations", IRLiteral("", 100, "int"))
            max_iter_expr = self._generate_expression(max_iterations_node, indent, flow)
            
            iter_count_var = f"iteration_count_{self._sanitize_name(step.node_id)}"
            code_lines.append(f"{indent}{iter_count_var} = 0")
            
            condition_code = self._generate_expression(condition_input, indent, flow)
            code_lines.append(f"{indent}while ({condition_code}) and {iter_count_var} < {max_iter_expr}:")
            code_lines.append(f"{indent}    {iter_count_var} += 1")
            
            body_steps = step.branches.get("body", [])
            if body_steps:
                for body_step in body_steps:
                    body_code = self._generate_step_code(body_step, indent + "    ", flow)
                    code_lines.extend(body_code)
            else:
                code_lines.append(f"{indent}    pass")
            
            code_lines.append(f"{indent}{py_control_var_name} = {{")
            code_lines.append(f"{indent}    'iterations_run': {iter_count_var},")
            code_lines.append(f"{indent}    'loop_ended_naturally': not ({condition_code}) if {iter_count_var} < {max_iter_expr} else False")
            code_lines.append(f"{indent}}}")

        elif control_type == "for_each":
            list_input = step.inputs.get("list", IRLiteral("", [], "list"))
            list_expr = self._generate_expression(list_input, indent, flow)
            iterator_name_node = step.inputs.get("iterator_name", IRLiteral("", "item", "str"))
            actual_iterator_name = self._get_actual_variable_name(iterator_name_node)
            iterator_index_var = f"{actual_iterator_name}_index"

            iter_count_var = f"iteration_count_{self._sanitize_name(step.node_id)}"
            for_each_list_var = f"for_each_list_{self._sanitize_name(step.node_id)}"
            
            code_lines.append(f"{indent}{iter_count_var} = 0")
            code_lines.append(f"{indent}{for_each_list_var} = {list_expr}")
            code_lines.append(f"{indent}for {iterator_index_var}, {actual_iterator_name} in enumerate({for_each_list_var}):")
            code_lines.append(f"{indent}    {iter_count_var} += 1")

            body_steps = step.branches.get("body", [])
            if body_steps:
                for body_step in body_steps:
                    body_code = self._generate_step_code(body_step, indent + "    ", flow)
                    code_lines.extend(body_code)
            else:
                code_lines.append(f"{indent}    pass")
            
            code_lines.append(f"{indent}{py_control_var_name} = {{")
            code_lines.append(f"{indent}    'iterations_completed': {iter_count_var}")
            code_lines.append(f"{indent}}}")

        elif control_type in ("try_catch", "try"):
            code_lines.append(f"{indent}try:")
            
            try_steps = step.branches.get("try", [])
            if try_steps:
                for try_step in try_steps:
                    try_code = self._generate_step_code(try_step, indent + "    ", flow)
                    code_lines.extend(try_code)
            else:
                code_lines.append(f"{indent}    pass")

            code_lines.append(f"{indent}    {py_control_var_name} = {{'success': True, 'error_details': None}}")
            code_lines.append(f"{indent}except Exception as e:")
            code_lines.append(f"{indent}    {py_control_var_name} = {{")
            code_lines.append(f"{indent}        'success': False,")
            code_lines.append(f"{indent}        'error_details': {{'type': type(e).__name__, 'message': str(e)}}")
            code_lines.append(f"{indent}    }}")
            
            catch_steps = step.branches.get("catch", [])
            if catch_steps:
                for catch_step in catch_steps:
                    catch_code = self._generate_step_code(catch_step, indent + "    ", flow)
                    code_lines.extend(catch_code)

        return code_lines

    def _generate_variable_operation_code(self, step: IRStep, indent: str, flow: IRFlow) -> List[str]:
        """Generate code for variable operations."""
        code_lines = []
        py_var_name_for_output = self._sanitize_name(self.step_var[step.node_id])

        if step.action in ("variables.set_local", "variables.set"):
            actual_target_var_name = py_var_name_for_output
            value_expr = self._generate_expression(step.inputs.get("value"), indent, flow)
            code_lines.append(f"{indent}{actual_target_var_name} = {value_expr}")

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
            name_node = step.inputs.get("name")
            if isinstance(name_node, IRLiteral) and isinstance(name_node.value, str):
                env_var_key_repr = repr(name_node.value)
            else:
                env_var_key_expr = self._generate_expression(name_node, indent, flow)
                env_var_key_repr = env_var_key_expr

            default_expr = self._generate_expression(step.inputs.get("default"), indent, flow)
            code_lines.append(f"{indent}{py_var_name_for_output} = os.environ.get({env_var_key_repr}, {default_expr})")

        return code_lines

    def _generate_basic_operation_code(self, step: IRStep, indent: str, flow: IRFlow) -> List[str]:
        """Generate code for basic mathematical operations."""
        code_lines = []
        op_map = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}
        action_name = step.action.split(".")[1]
        py_var_name_for_output = self._sanitize_name(self.step_var[step.node_id])

        if action_name in op_map:
            # Determine parameter names based on action
            param_map = {
                "add": ("a", "b"),
                "subtract": ("x", "y"),
                "multiply": ("x", "y"),
                "divide": ("x", "y")
            }
            lhs_param_name, rhs_param_name = param_map.get(action_name, ("operand1", "operand2"))

            # Get input nodes
            lhs_val_node = step.inputs.get(lhs_param_name, list(step.inputs.values())[0] if step.inputs else None)
            rhs_val_node = step.inputs.get(rhs_param_name, list(step.inputs.values())[1] if len(step.inputs) > 1 else None)

            if lhs_val_node and rhs_val_node:
                lhs = self._generate_expression(lhs_val_node, indent, flow)
                rhs = self._generate_expression(rhs_val_node, indent, flow)
                op_symbol = op_map[action_name]
                code_lines.append(f"{indent}{py_var_name_for_output} = {lhs} {op_symbol} {rhs}")
            else:
                code_lines.append(f"{indent}# Error: Missing operands for {step.action}")
                code_lines.append(f"{indent}{py_var_name_for_output} = None")
        else:
            code_lines.append(f"{indent}# Unsupported basic action: {step.action}")
            code_lines.append(f"{indent}{py_var_name_for_output} = None")

        return code_lines

    def _generate_integration_call_code(self, step: IRStep, indent: str, flow: IRFlow) -> List[str]:
        """Generate code for integration function calls."""
        code_lines = []
        py_var_name_for_output = self._sanitize_name(self.step_var[step.node_id])
        
        if "." in step.action:
            integration, action_name_str = step.action.split(".", 1)
            
            # Default module/function naming
            module_var_py = self._sanitize_name(integration)
            func_name_py = self._sanitize_name(action_name_str)

            # Try to get function call pattern from integration handler
            if self.integration_handler:
                call_str_template = self.integration_handler.get_function_call(
                    integration, action_name_str, "python")
                if call_str_template:
                    if "." in call_str_template:
                        mod_part, func_part = call_str_template.split(".", 1)
                        module_var_py = self._sanitize_name(mod_part)
                        func_name_py = self._sanitize_name(func_part)
                    else:
                        module_var_py = None
                        func_name_py = self._sanitize_name(call_str_template)
            
            # Build arguments
            arg_list = []
            for input_name, input_node in step.inputs.items():
                input_expr = self._generate_expression(input_node, indent, flow)
                arg_list.append(f"{self._sanitize_name(input_name)}={input_expr}")
            
            args_str = ", ".join(arg_list)
            
            # Generate function call
            if module_var_py:
                code_lines.append(f"{indent}{py_var_name_for_output} = {module_var_py}.{func_name_py}({args_str})")
            else:
                code_lines.append(f"{indent}{py_var_name_for_output} = {func_name_py}({args_str})")
        else:
            # Direct function call
            func_name_py = self._sanitize_name(step.action)
            arg_list = [self._generate_expression(val_node, indent, flow) for val_node in step.inputs.values()]
            args_str = ", ".join(arg_list)
            code_lines.append(f"{indent}# Direct function call: {step.action}")
            code_lines.append(f"{indent}{py_var_name_for_output} = {func_name_py}({args_str})")
        
        return code_lines

    def _parse_case_value(self, case_val_str: str):
        """Parse a case value string to its appropriate type."""
        try:
            return int(case_val_str)
        except ValueError:
            try:
                return float(case_val_str)
            except ValueError:
                if case_val_str.lower() == "true":
                    return True
                elif case_val_str.lower() == "false":
                    return False
                else:
                    return case_val_str

    def _generate_expression(self, node: Any, indent: str, flow: IRFlow) -> str:
        """Generate a Python expression from an IR node."""
        if node is None:
            return "None"
            
        if isinstance(node, IRLiteral):
            if node.value_type == "expression":
                return str(node.value)
            else:
                return repr(node.value)
                
        elif isinstance(node, IRVariableRef):
            source_name_sanitized = self._sanitize_name(node.source_name)
            
            if node.source_type == "env":
                return f"os.environ.get({repr(node.source_name)}, '')"
                
            elif node.source_type == "flow_var":
                return source_name_sanitized
                
            elif node.source_type == "step":
                step_py_var_name = self.step_var.get(node.source_name, source_name_sanitized)
                referenced_step = flow.get_step_by_id(node.source_name)
                
                # Check if step produces direct values or dictionaries
                is_direct_value_type = False
                if referenced_step:
                    action = referenced_step.action
                    if (action.startswith("variables.") or 
                        action.startswith("basic.") or
                        action in ("variables.set", "variables.get", "variables.get_env")):
                        is_direct_value_type = True
                
                if is_direct_value_type:
                    return step_py_var_name
                else:
                    if node.field_path:
                        return f"{step_py_var_name}['{node.field_path}']"
                    else:
                        return step_py_var_name
                    
        elif isinstance(node, IRTemplate):
            return self._generate_template_expression(node, indent, flow)
        
        return repr(str(node))

    def _generate_template_expression(self, node: IRTemplate, indent: str, flow: IRFlow) -> str:
        """Generate a Python f-string from a template node."""
        f_string_content = node.template
        
        # Process expressions and create replacement map
        for i, expr_node_in_template in enumerate(node.expressions):
            py_expr_for_template = self._generate_expression(expr_node_in_template, indent, flow)
            
            # Find and replace the original placeholder
            original_placeholder_found = False
            if isinstance(expr_node_in_template, IRVariableRef):
                ref_src_type = expr_node_in_template.source_type
                ref_src_name = expr_node_in_template.source_name
                ref_field = expr_node_in_template.field_path

                possible_placeholders = []
                if ref_src_type == "flow_var":
                    possible_placeholders.extend([
                        f"{{{{var.{ref_src_name}}}}}",
                        f"{{{{local.{ref_src_name}}}}}",
                        f"{{{ref_src_name}}}"
                    ])
                elif ref_src_type == "env":
                    possible_placeholders.append(f"{{{{env.{ref_src_name}}}}}")
                elif ref_src_type == "step":
                    if ref_field:
                        possible_placeholders.append(f"{{{{{ref_src_name}.{ref_field}}}}}")
                    else:
                        possible_placeholders.append(f"{{{{{ref_src_name}}}}}")
                
                # Also check single-brace versions
                single_brace_placeholders = [ph.replace("{{", "{").replace("}}", "}") for ph in possible_placeholders]
                possible_placeholders.extend(single_brace_placeholders)
                
                for ph_to_replace in possible_placeholders:
                    if ph_to_replace in f_string_content:
                        f_string_content = f_string_content.replace(ph_to_replace, f"{{{py_expr_for_template}}}")
                        original_placeholder_found = True
                        break
            
            if not original_placeholder_found:
                # Fallback: replace any remaining {{ }} with single braces for f-string
                pass

        # Handle remaining literal braces
        f_string_content = f_string_content.replace("{{", "{{").replace("}}", "}}")
        
        # Return as f-string
        if '\n' in f_string_content:
            return f'f"""{f_string_content}"""'
        else:
            return f'f"{f_string_content}"'

# Utility function to generate Mermaid diagrams (maintaining backward compatibility)
def generate_mermaid(flow: IRFlow) -> str:
    """Generate a Mermaid diagram from an IR flow."""
    lines = ["flowchart TD"]
    
    for step in flow.steps:
        step_id = step.node_id
        action = step.action
        
        # Create node
        if isinstance(step, IRControlFlow):
            lines.append(f"    {step_id}[{{{step_id}<br/>{action}}}]")
        else:
            lines.append(f"    {step_id}[{step_id}<br/>{action}]")
        
        # Add connections based on step type
        if isinstance(step, IRControlFlow):
            if step.control_type in ("if_node", "if"):
                if "then" in step.branches:
                    then_steps = step.branches["then"]
                    if then_steps:
                        lines.append(f"    {step_id} -->|Yes| {then_steps[0].node_id}")
                
                if "else" in step.branches:
                    else_steps = step.branches["else"]
                    if else_steps:
                        lines.append(f"    {step_id} -->|No| {else_steps[0].node_id}")
            
            elif step.control_type == "switch":
                for case_name, case_steps in step.branches.items():
                    if case_steps:
                        label = case_name.replace("case_", "") if case_name.startswith("case_") else case_name
                        lines.append(f"    {step_id} -->|{label}| {case_steps[0].node_id}")
        
        else:
            # Regular step - connect to next step if any
            current_index = flow.steps.index(step)
            if current_index < len(flow.steps) - 1:
                next_step = flow.steps[current_index + 1]
                lines.append(f"    {step_id} --> {next_step.node_id}")
    
    return "\n".join(lines)