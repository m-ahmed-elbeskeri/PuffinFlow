"""FlowForge Code Generation Package."""

__version__ = "0.1.0"

from .ir import (
    IRNode, IRNodeType, IRFlow, IRStep, IRControlFlow, 
    IRVariableRef, IRLiteral, IRTemplate
)
from .ir_builder import IRBuilder
from .python_printer import PythonPrinter
from .typescript_printer import TypeScriptPrinter
from .validator import FlowValidator, ValidationIssue
from .codegen import CodeGenerator
from .integration_handler import IntegrationHandler

__all__ = [
    # IR Classes
    "IRNode", "IRNodeType", "IRFlow", "IRStep", "IRControlFlow", 
    "IRVariableRef", "IRLiteral", "IRTemplate",
    
    # Builder
    "IRBuilder",
    
    # Printers
    "PythonPrinter", "TypeScriptPrinter",
    
    # Validator
    "FlowValidator", "ValidationIssue",
    
    # High-level API
    "CodeGenerator",
    
    # Integration Handler
    "IntegrationHandler"
]