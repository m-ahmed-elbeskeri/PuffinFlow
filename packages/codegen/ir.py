
"""Intermediate Representation (IR) for FlowForge flows and steps."""

from typing import Dict, List, Any, Optional, Union, Set
from enum import Enum

class IRNodeType(Enum):
    """Type of IR node."""
    FLOW = "flow"
    STEP = "step"
    CONTROL_FLOW = "control_flow"
    VARIABLE_REF = "variable_ref"
    LITERAL = "literal"
    TEMPLATE = "template"

class IRNode:
    """Base class for all IR nodes."""
    def __init__(self, node_type: IRNodeType, node_id: str):
        self.node_type = node_type
        self.node_id = node_id
        self.metadata: Dict[str, Any] = {}

class IRFlow(IRNode):
    """Represents a complete flow."""
    def __init__(self, flow_id: str):
        super().__init__(IRNodeType.FLOW, flow_id)
        self.steps: List['IRStep'] = []
        self._step_map: Dict[str, 'IRStep'] = {} # Added for quick lookup
        self.variables: Dict[str, Any] = {}
        self.environment: Dict[str, str] = {}
        
    def add_step(self, step: 'IRStep'):
        """Add a step to the flow."""
        self.steps.append(step)
        if step.node_id: # Ensure step_id is present before adding to map
            self._step_map[step.node_id] = step # Populate the map

    def get_step_by_id(self, step_id: str) -> Optional['IRStep']:
        """Get a step by its ID."""
        return self._step_map.get(step_id)

class IRStep(IRNode):
    """Represents a single step in a flow."""
    def __init__(self, step_id: str, action: str):
        super().__init__(IRNodeType.STEP, step_id)
        self.action = action
        self.inputs: Dict[str, IRNode] = {}
        self.outputs: Dict[str, Any] = {}  # Output schema
        self.next_steps: List[Dict[str, Union[str, 'IRStep']]] = []
        
    def add_input(self, name: str, value: IRNode):
        """Add an input to the step."""
        self.inputs[name] = value
        
    def add_output(self, name: str, schema: Any):
        """Add an output to the step."""
        self.outputs[name] = schema
        
    def add_next_step(self, condition: Optional[IRNode], target: Union[str, 'IRStep']):
        """Add a possible next step with an optional condition."""
        self.next_steps.append({"condition": condition, "target": target})

class IRControlFlow(IRStep):
    """Represents a control flow structure (if, loop, etc.)."""
    def __init__(self, step_id: str, control_type: str):
        action = f"control.{control_type}"
        super().__init__(step_id, action)
        self.control_type = control_type
        self.branches: Dict[str, List[IRStep]] = {}
        
    def add_branch(self, branch_name: str, steps: List[IRStep]):
        """Add a branch to the control flow structure."""
        self.branches[branch_name] = steps

class IRVariableRef(IRNode):
    """Represents a reference to a variable or step output."""
    def __init__(self, ref_id: str, source_type: str, source_name: str, field_path: Optional[str] = None):
        super().__init__(IRNodeType.VARIABLE_REF, ref_id)
        self.source_type = source_type  # 'step', 'env', 'flow_var', etc.
        self.source_name = source_name
        self.field_path = field_path
        
class IRLiteral(IRNode):
    """Represents a literal value."""
    def __init__(self, value_id: str, value: Any, value_type: str):
        super().__init__(IRNodeType.LITERAL, value_id)
        self.value = value
        self.value_type = value_type

class IRTemplate(IRNode):
    """Represents a template string with embedded expressions."""
    def __init__(self, template_id: str, template: str, expressions: List[IRNode]):
        super().__init__(IRNodeType.TEMPLATE, template_id)
        self.template = template
        self.expressions = expressions
