"""High-level API for FlowForge code generation."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple

from .ir import IRFlow
from .ir_builder import IRBuilder
from .python_printer import PythonPrinter
from .typescript_printer import TypeScriptPrinter
from .validator import FlowValidator

class CodeGenerator:
    """
    High-level API for generating code from flow definitions.
    """
    
    def __init__(self, registry=None, integration_handler=None):
        """
        Initialize the code generator.
        
        Args:
            registry: Optional FlowForge registry for action validation
            integration_handler: Optional integration handler for multi-language support
        """
        self.registry = registry
        self.integration_handler = integration_handler
        self.builder = IRBuilder(registry)
        self.validator = FlowValidator(registry)
    
    def validate_flow(self, flow_def: Union[Dict[str, Any], Path, str]) -> List[dict]:
        """
        Validate a flow definition and return issues.
        
        Args:
            flow_def: Flow definition as dict, path to YAML file, or YAML string
            
        Returns:
            List of validation issues as dictionaries
        """
        # Parse flow definition if needed
        flow_dict = self._parse_flow_def(flow_def)
        
        # Build IR
        ir_flow = self.builder.build_flow(flow_dict)
        
        # Validate
        issues = self.validator.validate_flow(ir_flow)
        
        # Convert issues to dicts for easy serialization
        return [
            {
                "node_id": issue.node_id,
                "issue_type": issue.issue_type,
                "message": issue.message,
                "severity": issue.severity
            }
            for issue in issues
        ]
    
    def generate_python(
        self, 
        flow_def: Union[Dict[str, Any], Path, str], 
        use_native_control: bool = True
    ) -> str:
        """
        Generate Python code for a flow.
        
        Args:
            flow_def: Flow definition as dict, path to YAML file, or YAML string
            use_native_control: Whether to use native Python control structures
            
        Returns:
            Generated Python code
        """
        # Parse flow definition if needed
        flow_dict = self._parse_flow_def(flow_def)
        
        # Build IR
        ir_flow = self.builder.build_flow(flow_dict)
        
        # Generate code
        printer = PythonPrinter(
            use_native_control=use_native_control,
            integration_handler=self.integration_handler
        )
        return printer.print_flow(ir_flow)
    
    def generate_typescript(
        self, 
        flow_def: Union[Dict[str, Any], Path, str], 
        output_type: str = "function",
        react_component: bool = False
    ) -> str:
        """
        Generate TypeScript code for a flow.
        
        Args:
            flow_def: Flow definition as dict, path to YAML file, or YAML string
            output_type: Type of output ("class", "function", or "react")
            react_component: Whether to generate a React component
            
        Returns:
            Generated TypeScript code
        """
        # Parse flow definition if needed
        flow_dict = self._parse_flow_def(flow_def)
        
        # Build IR
        ir_flow = self.builder.build_flow(flow_dict)
        
        # Generate code
        printer = TypeScriptPrinter(
            output_type=output_type, 
            react_component=react_component,
            integration_handler=self.integration_handler
        )
        return printer.print_flow(ir_flow)
    
    def generate_all(
        self, 
        flow_def: Union[Dict[str, Any], Path, str],
        output_dir: Optional[Path] = None,
        base_filename: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Generate all supported code outputs for a flow.
        
        Args:
            flow_def: Flow definition as dict, path to YAML file, or YAML string
            output_dir: Optional directory to write files to
            base_filename: Base filename for generated files
            
        Returns:
            Dictionary of language to generated code
        """
        # Parse flow definition if needed
        flow_dict = self._parse_flow_def(flow_def)
        flow_id = flow_dict.get("id", "flow")
        
        if base_filename is None:
            base_filename = flow_id
        
        # Build IR
        ir_flow = self.builder.build_flow(flow_dict)
        
        # Generate code for all targets
        outputs = {}
        
        # Python
        python_printer = PythonPrinter(use_native_control=True, integration_handler=self.integration_handler)
        python_code = python_printer.print_flow(ir_flow)
        outputs["python"] = python_code
        
        # TypeScript - Function
        ts_func_printer = TypeScriptPrinter(output_type="function", react_component=False, integration_handler=self.integration_handler)
        ts_func_code = ts_func_printer.print_flow(ir_flow)
        outputs["typescript_function"] = ts_func_code
        
        # TypeScript - Class
        ts_class_printer = TypeScriptPrinter(output_type="class", react_component=False, integration_handler=self.integration_handler)
        ts_class_code = ts_class_printer.print_flow(ir_flow)
        outputs["typescript_class"] = ts_class_code
        
        # TypeScript - React
        ts_react_printer = TypeScriptPrinter(output_type="react", react_component=True, integration_handler=self.integration_handler)
        ts_react_code = ts_react_printer.print_flow(ir_flow)
        outputs["typescript_react"] = ts_react_code
        
        # Write to files if output_dir is provided
        if output_dir is not None:
            os.makedirs(output_dir, exist_ok=True)
            
            # Python file
            with open(output_dir / f"{base_filename}.py", "w") as f:
                f.write(python_code)
            
            # TypeScript files
            with open(output_dir / f"{base_filename}.ts", "w") as f:
                f.write(ts_func_code)
                
            with open(output_dir / f"{base_filename}_class.ts", "w") as f:
                f.write(ts_class_code)
                
            with open(output_dir / f"{base_filename}_react.tsx", "w") as f:
                f.write(ts_react_code)
        
        return outputs
    
    def generate_env_file(
        self, 
        flow_def: Union[Dict[str, Any], Path, str],
        output_path: Optional[Path] = None
    ) -> str:
        """
        Generate a .env file template for a flow.
        
        Args:
            flow_def: Flow definition as dict, path to YAML file, or YAML string
            output_path: Optional path to write .env file
            
        Returns:
            Generated .env file content
        """
        # Parse flow definition if needed
        flow_dict = self._parse_flow_def(flow_def)
        flow_id = flow_dict.get("id", "flow")
        
        # Build IR
        ir_flow = self.builder.build_flow(flow_dict)
        
        # Validate to collect environment variables
        self.validator.validate_flow(ir_flow)
        env_vars = self.validator.env_vars
        
        # Generate .env template
        lines = [
            f"# Environment variables for flow: {flow_id}",
            "# Fill in the values below for environment variables used in this flow",
            ""
        ]
        
        for var_name in sorted(env_vars):
            lines.append(f"{var_name}=")
        
        content = "\n".join(lines)
        
        # Write to file if path is provided
        if output_path is not None:
            with open(output_path, "w") as f:
                f.write(content)
        
        return content
    
    def _parse_flow_def(self, flow_def: Union[Dict[str, Any], Path, str]) -> Dict[str, Any]:
        """Parse flow definition from various formats."""
        if isinstance(flow_def, dict):
            return flow_def
        elif isinstance(flow_def, Path) or isinstance(flow_def, str) and os.path.exists(flow_def):
            # Load from file
            with open(flow_def, "r") as f:
                return yaml.safe_load(f)
        elif isinstance(flow_def, str):
            # Try to parse as YAML string
            return yaml.safe_load(flow_def)
        else:
            raise ValueError(f"Unsupported flow definition type: {type(flow_def)}")