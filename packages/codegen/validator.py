"""Validates IR flows and reports issues."""

from typing import Dict, List, Any, Set, Tuple, Optional # Added Optional here
from .ir import (
    IRFlow, IRStep, IRControlFlow, IRVariableRef, 
    IRLiteral, IRTemplate, IRNodeType,IRNode
)
# Import IntegrationHandler for fallback mechanism
from packages.codegen.integration_handler import IntegrationHandler # Assuming this path is correct relative to validator.py
from pathlib import Path

class ValidationIssue:
    """Represents a validation issue found in the flow."""
    
    def __init__(self, node_id: str, issue_type: str, message: str, severity: str = "error"):
        self.node_id = node_id
        self.issue_type = issue_type
        self.message = message
        self.severity = severity
    
    def __str__(self):
        return f"{self.severity.upper()}: [{self.node_id}] {self.issue_type} - {self.message}"

class FlowValidator:
    """Validates IR flows and reports issues."""
    
    def __init__(self, registry=None):
        """
        Initialize the validator.
        
        Args:
            registry: Optional registry for validating actions and inputs
        """
        self.registry = registry
        self.issues: List[ValidationIssue] = []
        self.env_vars: Set[str] = set()
        self.flow_vars: Set[str] = set()
        self._fallback_ih: Optional[IntegrationHandler] = None # For lazy initialization
    
    def _get_fallback_ih(self) -> Optional[IntegrationHandler]:
        """Lazy-initializes and returns a fallback IntegrationHandler."""
        if self._fallback_ih is None:
            try:
                # IntegrationHandler defaults to "./integrations" relative to CWD
                # This path needs to be correct for where IntegrationHandler expects to find manifests.
                # If IntegrationHandler is in the same 'codegen' package, './integrations' might refer to 'codegen/integrations'
                # or if run from root, it refers to 'ROOT/integrations'.
                # Let's assume the default path in IntegrationHandler is robust.
                self._fallback_ih = IntegrationHandler() 
                if not self._fallback_ih.manifests: # Check if it actually loaded anything
                    print("Warning: Fallback IntegrationHandler loaded no manifests. Ensure './integrations' directory is correct or accessible from current working directory.")
            except Exception as e:
                print(f"Warning: Could not initialize fallback IntegrationHandler: {e}")
                # Create a dummy object to prevent repeated errors if init fails
                class DummyIH:
                    manifests: Dict[str, Any] = {} # Added type hint for clarity
                self._fallback_ih = DummyIH() 
        return self._fallback_ih

    def validate_flow(self, flow: IRFlow) -> List[ValidationIssue]:
        """
        Validate a flow and return a list of issues.
        
        Args:
            flow: The IR flow to validate
            
        Returns:
            List of validation issues
        """
        self.issues = []
        self.env_vars = set()
        self.flow_vars = set()
        
        # Validate flow basics
        if not flow.node_id:
            self.issues.append(ValidationIssue("flow", "missing_id", "Flow is missing an ID"))
        
        if not flow.steps:
            self.issues.append(ValidationIssue(flow.node_id, "empty_flow", "Flow has no steps", "warning"))
        
        # Track steps and variables for reference validation
        step_ids = set(step.node_id for step in flow.steps)
        
        # Validate each step
        for step in flow.steps:
            self._validate_step(step, step_ids)
        
        # Check for unused flow variables
        used_flow_vars = set()
        for step in flow.steps:
            used_flow_vars.update(self._collect_used_variables(step))
        
        # Only warn for unused variables if they were explicitly set
        # Variables referenced (e.g. in templates) but never set are caught by "undefined_variable"
        unused_vars = self.flow_vars - used_flow_vars
        if unused_vars:
            var_list = ", ".join(sorted(list(unused_vars))) # Sort for consistent output
            self.issues.append(ValidationIssue(
                flow.node_id, 
                "unused_variables", 
                f"Flow has unused variables that were set: {var_list}", 
                "warning"
            ))
        
        return self.issues
    
    def _validate_step(self, step: IRStep, all_step_ids: Set[str]):
        """Validate a single step."""
        # Check step ID
        if not step.node_id:
            self.issues.append(ValidationIssue("unknown", "missing_id", "Step is missing an ID"))
            return
        
        # Check step action
        if not step.action:
            self.issues.append(ValidationIssue(step.node_id, "missing_action", "Step is missing an action"))
            # If action is missing, further validation of action is not possible
            return 
        
        # Validate action with registry if available
        if "." in step.action: # Only try to validate if it looks like an integration action
            integration, action_name = step.action.split(".", 1)
            
            integration_manifest = None
            source_of_manifest = "provided registry"

            if self.registry:
                # Try finding in the provided registry first (checking for common attributes)
                if hasattr(self.registry, 'integrations') and isinstance(self.registry.integrations, dict) and \
                   integration in self.registry.integrations:
                    integration_manifest = self.registry.integrations[integration]
                elif hasattr(self.registry, 'manifests') and isinstance(self.registry.manifests, dict) and \
                     integration in self.registry.manifests: # E.g. if registry is an IntegrationHandler itself
                    integration_manifest = self.registry.manifests[integration]
            
            if not integration_manifest:
                # If not found in provided registry (or no registry provided), try the fallback IntegrationHandler
                fallback_ih = self._get_fallback_ih()
                if fallback_ih and hasattr(fallback_ih, 'manifests') and \
                   integration in fallback_ih.manifests:
                    integration_manifest = fallback_ih.manifests[integration]
                    source_of_manifest = "fallback default integrations path"
            
            if not integration_manifest:
                self.issues.append(ValidationIssue(
                    step.node_id, 
                    "unknown_integration", 
                    f"Step uses unknown integration '{integration}'. Not found in provided registry or default integration paths."
                ))
            else:
                # Check if action exists in the found manifest
                integration_actions = integration_manifest.get('actions', {})
                if action_name not in integration_actions:
                    self.issues.append(ValidationIssue(
                        step.node_id, 
                        "unknown_action", 
                        f"Step uses unknown action '{action_name}' in integration '{integration}' (manifest source: {source_of_manifest})."
                    ))
                else:
                    # Validate required inputs
                    action_def = integration_actions[action_name]
                    self._validate_inputs(step, action_def)
        
        # Handle variable operations
        if step.action.startswith("variables."):
            if step.action in ("variables.set_local", "variables.set"):
                # Track variable being set
                name_node = step.inputs.get("name")
                if isinstance(name_node, IRLiteral) and isinstance(name_node.value, str) and name_node.value:
                    self.flow_vars.add(name_node.value)
                
            elif step.action == "variables.get_env":
                # Track environment variable being accessed
                name_node = step.inputs.get("name")
                if isinstance(name_node, IRLiteral) and isinstance(name_node.value, str) and name_node.value:
                    self.env_vars.add(name_node.value)
        
        # Validate control flow specific aspects
        if isinstance(step, IRControlFlow):
            self._validate_control_flow(step, all_step_ids)
        
        # Validate input values
        for input_name, input_value in step.inputs.items():
            self._validate_input_value(step.node_id, input_name, input_value, all_step_ids)
    
    def _validate_inputs(self, step: IRStep, action_def: Dict[str, Any]):
        """Validate that a step has all required inputs for its action."""
        action_inputs_def = action_def.get('inputs', {}) # Renamed to avoid conflict
        
        # Check for required inputs
        for input_name, input_def in action_inputs_def.items():
            if isinstance(input_def, dict) and input_def.get('required', False):
                if input_name not in step.inputs:
                    self.issues.append(ValidationIssue(
                        step.node_id, 
                        "missing_required_input", 
                        f"Step is missing required input '{input_name}' for action '{step.action}'"
                    ))
    
    def _validate_control_flow(self, step: IRControlFlow, all_step_ids: Set[str]):
        """Validate control flow specific aspects."""
        control_type = step.control_type
        
        if control_type in ("if_node", "if"):
            # Check if condition is present
            if "condition" not in step.inputs:
                self.issues.append(ValidationIssue(
                    step.node_id, 
                    "missing_condition", 
                    f"Control flow '{control_type}' is missing a condition"
                ))
            
            # Check if then/else steps exist (Note: IR branches are lists of IRSteps, not just IDs)
            for branch_type, branch_steps_list in step.branches.items(): # e.g. "then", "else"
                if branch_steps_list: # If the branch has steps
                    for branch_step_node in branch_steps_list:
                         # IR structure has IRStep objects in branches, not IDs.
                         # This check might be redundant if IR construction guarantees valid step objects.
                         # However, keeping it for robustness or if IR structure changes.
                        if branch_step_node.node_id not in all_step_ids:
                            self.issues.append(ValidationIssue(
                                step.node_id, 
                                "invalid_branch_step", 
                                f"Control flow '{control_type}' branch '{branch_type}' references non-existent step '{branch_step_node.node_id}'"
                            ))
        
        elif control_type == "switch":
            # Check if value is present
            if "value" not in step.inputs:
                self.issues.append(ValidationIssue(
                    step.node_id, 
                    "missing_value", 
                    f"Control flow '{control_type}' is missing a value"
                ))
            
            for branch_name, branch_steps_list in step.branches.items():
                for branch_step_node in branch_steps_list:
                    if branch_step_node.node_id not in all_step_ids:
                        self.issues.append(ValidationIssue(
                            step.node_id, 
                            "invalid_branch_step", 
                            f"Control flow '{control_type}' branch '{branch_name}' references non-existent step '{branch_step_node.node_id}'"
                        ))
        
        elif control_type in ("while_loop", "while", "for_each"): # Added for_each
            # Check if condition is present for while loops
            if control_type in ("while_loop", "while") and "condition" not in step.inputs:
                self.issues.append(ValidationIssue(
                    step.node_id, 
                    "missing_condition", 
                    f"Control flow '{control_type}' is missing a condition"
                ))
            
            # Check max_iterations for while loops to prevent infinite loops
            if control_type in ("while_loop", "while") and "max_iterations" not in step.inputs:
                self.issues.append(ValidationIssue(
                    step.node_id, 
                    "missing_max_iterations", 
                    f"Control flow '{control_type}' is missing max_iterations, which could lead to infinite loops",
                    "warning"
                ))
            
            # Check for body steps (common for all loop types)
            body_branch_name = "body" # Default branch name for loop bodies
            if body_branch_name not in step.branches or not step.branches[body_branch_name]:
                self.issues.append(ValidationIssue(
                    step.node_id,
                    "empty_loop_body",
                    f"Control flow '{control_type}' has an empty '{body_branch_name}' branch.",
                    "warning"
                ))
            else:
                for body_step_node in step.branches[body_branch_name]:
                    if body_step_node.node_id not in all_step_ids:
                         self.issues.append(ValidationIssue(
                            step.node_id, 
                            "invalid_branch_step", 
                            f"Control flow '{control_type}' branch '{body_branch_name}' references non-existent step '{body_step_node.node_id}'"
                        ))
    
    def _validate_input_value(self, step_id: str, input_name: str, input_value: Any, all_step_ids: Set[str]):
        """Validate an input value. Input_value is an IRNode."""
        if isinstance(input_value, IRVariableRef):
            # Validate variable reference
            if input_value.source_type == "step":
                # Check if referenced step exists
                if input_value.source_name not in all_step_ids:
                    self.issues.append(ValidationIssue(
                        step_id, 
                        "invalid_step_reference", 
                        f"Input '{input_name}' references non-existent step '{input_value.source_name}'"
                    ))
            
            elif input_value.source_type == "flow_var":
                # Track variable being accessed
                if input_value.source_name:
                    used_var = input_value.source_name
                    # A variable is considered defined if it has been set by variables.set_local/set
                    # or if it's a known input to the flow (not tracked here yet, but self.flow_vars tracks set variables)
                    if used_var not in self.flow_vars:
                        # This can be a common warning if flow inputs are not pre-declared in self.flow_vars
                        # For example, if a flow expects an input `user_name` passed at runtime.
                        self.issues.append(ValidationIssue(
                            step_id, 
                            "undefined_variable_reference", 
                            f"Input '{input_name}' references flow variable '{used_var}' which has not been explicitly set within the flow. (This may be an external input).",
                            "warning" 
                        ))
            
            elif input_value.source_type == "env":
                # Track environment variable being accessed
                if input_value.source_name:
                    self.env_vars.add(input_value.source_name)
        
        elif isinstance(input_value, IRTemplate):
            # Validate template expressions
            for expr in input_value.expressions:
                self._validate_input_value(step_id, f"{input_name}[template_expr:{expr.node_id}]", expr, all_step_ids)
    
    def _collect_used_variables(self, step: IRStep) -> Set[str]:
        """Collect all flow variables used in a step's inputs."""
        used_vars = set()
        
        # Check inputs for variable references
        for input_name, input_value_node in step.inputs.items(): # input_value_node is an IRNode
            used_vars.update(self._collect_variables_from_value_node(input_value_node))
        
        return used_vars
    
    def _collect_variables_from_value_node(self, value_node: Optional[IRNode]) -> Set[str]: # value_node can be None for optional IRNode fields
        """Collect variables used in an IRNode value."""
        used_vars = set()
        if value_node is None:
            return used_vars
        
        if isinstance(value_node, IRVariableRef):
            if value_node.source_type == "flow_var" and value_node.source_name:
                used_vars.add(value_node.source_name)
        
        elif isinstance(value_node, IRTemplate):
            for expr_node in value_node.expressions: # expr_node is an IRNode
                used_vars.update(self._collect_variables_from_value_node(expr_node))
        
        return used_vars