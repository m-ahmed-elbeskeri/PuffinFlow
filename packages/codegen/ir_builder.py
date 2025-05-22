"""Builder for converting flow definitions to IR."""

from typing import Dict, List, Any, Optional, Union
import re
import uuid

from .ir import (
    IRFlow, IRStep, IRControlFlow, IRVariableRef, 
    IRLiteral, IRTemplate, IRNodeType, IRNode
)

class IRBuilder:
    """Builds IR from flow definitions."""
    
    def __init__(self, registry=None):
        self.registry = registry
        self.id_counter = 0
        
    def _generate_id(self, prefix="id"):
        """Generate a unique ID for an IR node."""
        self.id_counter += 1
        return f"{prefix}_{self.id_counter}"
        
    def build_flow(self, flow_def: Dict[str, Any]) -> IRFlow:
        """Convert a flow definition to an IR flow."""
        flow_id = flow_def.get("id", "flow")
        flow = IRFlow(flow_id)
        
        # Process steps
        steps = flow_def.get("steps", [])
        step_ir_map = {}
        
        # First pass: create basic step nodes
        for step_def in steps:
            step_id = step_def.get("id")
            action = step_def.get("action", "")
            
            if action.startswith("control."):
                control_type = action.split(".", 1)[1]
                step = IRControlFlow(step_id, control_type)
            else:
                step = IRStep(step_id, action)
                
            step_ir_map[step_id] = step
            flow.add_step(step)
            
        # Second pass: process inputs and connections
        for step_def in steps:
            step_id = step_def.get("id")
            step = step_ir_map[step_id]
            inputs = step_def.get("inputs", {})
            
            # Process inputs
            for input_name, input_value in inputs.items():
                ir_value = self._process_input_value(input_value, step_ir_map)
                step.add_input(input_name, ir_value)
                
            # Process control flow for special steps
            if isinstance(step, IRControlFlow):
                self._process_control_flow(step, step_def, step_ir_map)
            else:
                # For regular steps, find next step by position in list
                step_index = next((i for i, s in enumerate(steps) if s.get("id") == step_id), -1)
                if step_index >= 0 and step_index < len(steps) - 1:
                    next_step_id = steps[step_index + 1].get("id")
                    if next_step_id in step_ir_map:
                        step.add_next_step(None, step_ir_map[next_step_id])
                        
        return flow
        
    def _process_input_value(self, value: Any, step_map: Dict[str, IRStep]) -> IRNode:
        """Convert an input value to an IR node."""
        if isinstance(value, (int, float, bool)) or value is None:
            # Literal value
            value_type = type(value).__name__
            return IRLiteral(self._generate_id("lit"), value, value_type)
            
        elif isinstance(value, str):
            # Check if it's a reference to a step output
            if "." in value and not value.startswith("'") and not value.startswith('"'):
                parts = value.split(".", 1)
                if len(parts) == 2:
                    source, field = parts
                    
                    if source == "env":
                        return IRVariableRef(self._generate_id("ref"), "env", field)
                    elif source in ("var", "local"):
                        return IRVariableRef(self._generate_id("ref"), "flow_var", field)
                    elif source in step_map:
                        return IRVariableRef(self._generate_id("ref"), "step", source, field)
            
            # Check if it's a template string
            if "{{" in value or "{" in value:
                template_pattern = r"\{\{([\s\S]+?)\}\}|\{([\s\S]+?)\}"
                matches = re.findall(template_pattern, value)
                
                if matches:
                    expressions = []
                    for match in matches:
                        content = match[0] if match[0] else match[1]
                        if content.startswith("env."):
                            env_var = content[4:]
                            expressions.append(IRVariableRef(self._generate_id("ref"), "env", env_var))
                        elif content.startswith("var.") or content.startswith("local."):
                            var_name = content.split(".", 1)[1]
                            expressions.append(IRVariableRef(self._generate_id("ref"), "flow_var", var_name))
                        elif "." in content:
                            # Likely a step reference
                            parts = content.split(".", 1)
                            if len(parts) == 2:
                                source, field = parts
                                if source in step_map:
                                    expressions.append(IRVariableRef(self._generate_id("ref"), "step", source, field))
                                else:
                                    # Just treat as expression
                                    expressions.append(IRLiteral(self._generate_id("lit"), content, "expression"))
                        else:
                            # Simple variable or expression
                            expressions.append(IRLiteral(self._generate_id("lit"), content, "expression"))
                            
                    return IRTemplate(self._generate_id("tmpl"), value, expressions)
            
            # Just a string literal
            return IRLiteral(self._generate_id("lit"), value, "str")
            
        elif isinstance(value, dict):
            # Convert dictionary values
            return IRLiteral(self._generate_id("lit"), str(value), "dict")
            
        elif isinstance(value, list):
            # Convert list values
            return IRLiteral(self._generate_id("lit"), str(value), "list")
            
        # Default fallback
        return IRLiteral(self._generate_id("lit"), str(value), "unknown")
    
    def _process_control_flow(self, step: IRControlFlow, step_def: Dict[str, Any], step_map: Dict[str, IRStep]):
        """Process control flow specific details."""
        control_type = step.control_type
        inputs = step_def.get("inputs", {})
        
        if control_type in ("if_node", "if"):
            # Process then/else branches
            then_step_id = inputs.get("then_step")
            else_step_id = inputs.get("else_step")
            
            if then_step_id and then_step_id in step_map:
                step.add_branch("then", [step_map[then_step_id]])
                step.add_next_step(IRLiteral(self._generate_id("lit"), True, "bool"), step_map[then_step_id])
                
            if else_step_id and else_step_id in step_map:
                step.add_branch("else", [step_map[else_step_id]])
                step.add_next_step(IRLiteral(self._generate_id("lit"), False, "bool"), step_map[else_step_id])
                
        elif control_type == "switch":
            # Process switch cases
            cases = inputs.get("cases", {})
            default = inputs.get("default")
            
            if isinstance(cases, dict):
                for case_val, target_id in cases.items():
                    if target_id in step_map:
                        case_condition = IRLiteral(self._generate_id("lit"), case_val, type(case_val).__name__)
                        step.add_branch(f"case_{case_val}", [step_map[target_id]])
                        step.add_next_step(case_condition, step_map[target_id])
                        
            if default and default in step_map:
                step.add_branch("default", [step_map[default]])
                step.add_next_step(IRLiteral(self._generate_id("lit"), "default", "str"), step_map[default])
                
        elif control_type in ("for_each", "while_loop", "while"):
            # Process subflow
            subflow = inputs.get("subflow", [])
            
            if isinstance(subflow, list):
                subflow_steps = []
                
                if all(isinstance(item, str) for item in subflow):
                    # List of step IDs
                    for sub_id in subflow:
                        if sub_id in step_map:
                            subflow_steps.append(step_map[sub_id])
                elif all(isinstance(item, dict) and "id" in item for item in subflow):
                    # List of step definitions (inline)
                    # This would need more complex handling for inline steps
                    pass
                    
                if subflow_steps:
                    step.add_branch("body", subflow_steps)
                    
        elif control_type in ("try_catch", "try"):
            # Process try/catch blocks
            try_block = inputs.get("subflow", inputs.get("try_body", []))
            catch_block = inputs.get("on_error", inputs.get("catch_handler", []))
            
            try_steps = []
            catch_steps = []
            
            # Process try block
            if isinstance(try_block, list):
                if all(isinstance(item, str) for item in try_block):
                    for sub_id in try_block:
                        if sub_id in step_map:
                            try_steps.append(step_map[sub_id])
                            
            # Process catch block
            if isinstance(catch_block, list):
                if all(isinstance(item, str) for item in catch_block):
                    for sub_id in catch_block:
                        if sub_id in step_map:
                            catch_steps.append(step_map[sub_id])
                            
            if try_steps:
                step.add_branch("try", try_steps)
            if catch_steps:
                step.add_branch("catch", catch_steps)