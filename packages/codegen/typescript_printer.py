"""Generates TypeScript code from IR."""

from typing import Dict, List, Any, Optional, Set, Tuple
import json
from .ir import (
    IRFlow, IRStep, IRControlFlow, IRVariableRef, 
    IRLiteral, IRTemplate, IRNodeType
)

class TypeScriptPrinter:
    """Generates TypeScript code from IR."""
    
    def __init__(self, output_type="class", react_component=False):
        """
        Initialize the TypeScript printer.
        
        Args:
            output_type: Type of output to generate ("class", "function", "react")
            react_component: Whether to generate a React component
        """
        self.output_type = output_type
        self.react_component = react_component
        self.step_var = {}  # Maps step ID to variable name
        self.imports = set()
        self.types = set()
        self.flow_variable_names = set()
        self.env_vars = set()
        
    def print_flow(self, flow: IRFlow) -> str:
        """Generate TypeScript code for a flow."""
        self.step_var = {step.node_id: f"{step.node_id}Result" for step in flow.steps}
        self.imports = set()
        self.types = set()
        self.flow_variable_names = set()
        self.env_vars = set()
        
        # Analyze flow to collect types, imports, etc.
        self._analyze_flow(flow)
        
        code_lines = []
        
        # Add imports
        if self.react_component:
            code_lines.append("import React, { useState, useEffect } from 'react';")
        
        if self.imports:
            for imp in sorted(self.imports):
                code_lines.append(imp)
                
        code_lines.append("")
        
        # Add type definitions
        if self.types:
            for typ in sorted(self.types):
                code_lines.append(typ)
                
            code_lines.append("")
        
        # Generate interface for flow result
        result_interface = self._generate_result_interface(flow)
        if result_interface:
            code_lines.extend(result_interface)
            code_lines.append("")
        
        if self.output_type == "class":
            # Generate class-based implementation
            code_lines.extend(self._generate_class_implementation(flow))
        elif self.output_type == "function":
            # Generate function-based implementation
            code_lines.extend(self._generate_function_implementation(flow))
        elif self.output_type == "react":
            # Generate React component implementation
            code_lines.extend(self._generate_react_implementation(flow))
        
        return "\n".join(code_lines)
    
    def _analyze_flow(self, flow: IRFlow):
        """Analyze the flow to collect types, imports, etc."""
        # Add basic types and imports
        self.types.add("interface StepResult { [key: string]: any; }")
        self.types.add("interface FlowVariables { [key: string]: any; }")
        
        # Collect environment variables
        for step in flow.steps:
            # Check for variable operations
            if step.action.startswith("variables."):
                if step.action == "variables.set_local" or step.action == "variables.set":
                    if "name" in step.inputs:
                        name_node = step.inputs["name"]
                        if isinstance(name_node, IRLiteral):
                            self.flow_variable_names.add(name_node.value)
                
                if step.action == "variables.get_env":
                    if "name" in step.inputs:
                        name_node = step.inputs["name"]
                        if isinstance(name_node, IRLiteral):
                            self.env_vars.add(name_node.value)
            
            # Analyze variable references in inputs
            for input_name, input_node in step.inputs.items():
                self._analyze_variable_references(input_node)
    
    def _analyze_variable_references(self, node):
        """Analyze variable references in a node."""
        if isinstance(node, IRVariableRef):
            if node.source_type == "env":
                self.env_vars.add(node.source_name)
            elif node.source_type == "flow_var":
                self.flow_variable_names.add(node.source_name)
        elif isinstance(node, IRTemplate):
            for expr in node.expressions:
                self._analyze_variable_references(expr)
    
    def _generate_result_interface(self, flow: IRFlow) -> List[str]:
        """Generate TypeScript interface for flow result."""
        lines = []
        
        if flow.steps:
            last_step = flow.steps[-1]
            lines.append(f"// Result interface for flow {flow.node_id}")
            lines.append(f"export interface {flow.node_id.capitalize()}Result {{")
            
            # Add interface properties based on last step outputs
            # For simplicity, we're using 'any' types here - in a real implementation,
            # you'd want to be more specific based on registry-provided output schemas
            lines.append(f"  // Output from final step: {last_step.node_id}")
            lines.append(f"  [key: string]: any;")
            lines.append("}")
        
        return lines
    
    def _generate_class_implementation(self, flow: IRFlow) -> List[str]:
        """Generate TypeScript class implementation."""
        lines = []
        
        flow_class_name = flow.node_id.capitalize() + "Flow"
        result_type = flow.node_id.capitalize() + "Result"
        
        lines.append(f"/**")
        lines.append(f" * {flow_class_name} - TypeScript implementation of the flow")
        lines.append(f" */")
        lines.append(f"export class {flow_class_name} {{")
        lines.append(f"  private flowVariables: FlowVariables = {{}};")
        
        # Add environment variable getters
        if self.env_vars:
            lines.append("")
            lines.append("  /**")
            lines.append("   * Get environment variable with optional default value")
            lines.append("   */")
            lines.append("  private getEnv(name: string, defaultValue: string = ''): string {")
            lines.append("    if (typeof process !== 'undefined' && process.env) {")
            lines.append("      return process.env[name] || defaultValue;")
            lines.append("    } else if (typeof window !== 'undefined' && (window as any).env) {")
            lines.append("      return (window as any).env[name] || defaultValue;")
            lines.append("    }")
            lines.append("    return defaultValue;")
            lines.append("  }")
        
        # Add execute method
        lines.append("")
        lines.append("  /**")
        lines.append("   * Execute the flow")
        lines.append("   */")
        lines.append(f"  public async execute(inputs: any = {{}}): Promise<{result_type}> {{")
        lines.append("    // Initialize flow variables with inputs")
        lines.append("    this.flowVariables = { ...inputs };")
        
        # Add step execution code
        for step in flow.steps:
            step_code = self._generate_step_code(step, "    ")
            lines.extend(step_code)
        
        # Return result of final step
        if flow.steps:
            last_step = flow.steps[-1]
            lines.append(f"    return {self.step_var[last_step.node_id]};")
        else:
            lines.append("    return {};")
            
        lines.append("  }")
        lines.append("}")
        
        return lines
    
    def _generate_function_implementation(self, flow: IRFlow) -> List[str]:
        """Generate TypeScript function implementation."""
        lines = []
        
        flow_func_name = "execute" + flow.node_id.capitalize() + "Flow"
        result_type = flow.node_id.capitalize() + "Result"
        
        lines.append(f"/**")
        lines.append(f" * {flow_func_name} - Execute the flow with the given inputs")
        lines.append(f" */")
        lines.append(f"export async function {flow_func_name}(inputs: any = {{}}): Promise<{result_type}> {{")
        lines.append("  // Initialize flow variables with inputs")
        lines.append("  const flowVariables: FlowVariables = { ...inputs };")
        
        # Add environment variable helper
        if self.env_vars:
            lines.append("")
            lines.append("  /**")
            lines.append("   * Get environment variable with optional default value")
            lines.append("   */")
            lines.append("  function getEnv(name: string, defaultValue: string = ''): string {")
            lines.append("    if (typeof process !== 'undefined' && process.env) {")
            lines.append("      return process.env[name] || defaultValue;")
            lines.append("    } else if (typeof window !== 'undefined' && (window as any).env) {")
            lines.append("      return (window as any).env[name] || defaultValue;")
            lines.append("    }")
            lines.append("    return defaultValue;")
            lines.append("  }")
        
        # Add step execution code
        for step in flow.steps:
            step_code = self._generate_step_code(step, "  ")
            lines.extend(step_code)
        
        # Return result of final step
        if flow.steps:
            last_step = flow.steps[-1]
            lines.append(f"  return {self.step_var[last_step.node_id]};")
        else:
            lines.append("  return {};")
            
        lines.append("}")
        
        return lines
    
    def _generate_react_implementation(self, flow: IRFlow) -> List[str]:
        """Generate React component implementation."""
        lines = []
        
        component_name = flow.node_id.capitalize() + "FlowComponent"
        result_type = flow.node_id.capitalize() + "Result"
        
        # Add component props interface
        lines.append("interface FlowComponentProps {")
        lines.append("  inputs?: any;")
        lines.append("  onCompleted?: (result: any) => void;")
        lines.append("  autoRun?: boolean;")
        lines.append("}")
        lines.append("")
        
        lines.append(f"/**")
        lines.append(f" * {component_name} - React component for the flow")
        lines.append(f" */")
        lines.append(f"export const {component_name}: React.FC<FlowComponentProps> = ({{")
        lines.append("  inputs = {},")
        lines.append("  onCompleted,")
        lines.append("  autoRun = true")
        lines.append("}) => {")
        
        # Add state for flow variables and results
        lines.append("  const [flowVariables, setFlowVariables] = useState<FlowVariables>({ ...inputs });")
        lines.append("  const [isRunning, setIsRunning] = useState<boolean>(false);")
        lines.append(f"  const [result, setResult] = useState<{result_type} | null>(null);")
        lines.append("  const [error, setError] = useState<Error | null>(null);")
        
        # Add environment variable helper
        if self.env_vars:
            lines.append("")
            lines.append("  /**")
            lines.append("   * Get environment variable with optional default value")
            lines.append("   */")
            lines.append("  const getEnv = (name: string, defaultValue: string = ''): string => {")
            lines.append("    if (typeof process !== 'undefined' && process.env) {")
            lines.append("      return process.env[name] || defaultValue;")
            lines.append("    } else if (typeof window !== 'undefined' && (window as any).env) {")
            lines.append("      return (window as any).env[name] || defaultValue;")
            lines.append("    }")
            lines.append("    return defaultValue;")
            lines.append("  };")
        
        # Add executeFlow function
        lines.append("")
        lines.append("  /**")
        lines.append("   * Execute the flow")
        lines.append("   */")
        lines.append("  const executeFlow = async (): Promise<void> => {")
        lines.append("    try {")
        lines.append("      setIsRunning(true);")
        lines.append("      setError(null);")
        
        # Generate step code
        for step in flow.steps:
            step_code = self._generate_step_code(step, "      ")
            lines.extend(step_code)
        
        # Set result from final step
        if flow.steps:
            last_step = flow.steps[-1]
            lines.append(f"      const finalResult = {self.step_var[last_step.node_id]};")
            lines.append("      setResult(finalResult);")
            lines.append("      if (onCompleted) {")
            lines.append("        onCompleted(finalResult);")
            lines.append("      }")
        else:
            lines.append("      setResult({});")
            lines.append("      if (onCompleted) {")
            lines.append("        onCompleted({});")
            lines.append("      }")
        
        lines.append("    } catch (err) {")
        lines.append("      setError(err instanceof Error ? err : new Error(String(err)));")
        lines.append("    } finally {")
        lines.append("      setIsRunning(false);")
        lines.append("    }")
        lines.append("  };")
        
        # Add useEffect for auto-running
        lines.append("")
        lines.append("  // Auto-run on mount if enabled")
        lines.append("  useEffect(() => {")
        lines.append("    if (autoRun) {")
        lines.append("      executeFlow();")
        lines.append("    }")
        lines.append("  }, [autoRun]);")
        
        # Add component render
        lines.append("")
        lines.append("  return (")
        lines.append('    <div className="flow-component">')
        lines.append('      {isRunning && <div className="flow-running">Running flow...</div>}')
        lines.append('      {error && <div className="flow-error">Error: {error.message}</div>}')
        lines.append("      {!isRunning && !autoRun && (")
        lines.append('        <button onClick={executeFlow} className="flow-run-button">')
        lines.append("          Run Flow")
        lines.append("        </button>")
        lines.append("      )}")
        lines.append("      {result && (")
        lines.append('        <div className="flow-result">')
        lines.append("          <h3>Flow Result:</h3>")
        lines.append("          <pre>{JSON.stringify(result, null, 2)}</pre>")
        lines.append("        </div>")
        lines.append("      )}")
        lines.append("    </div>")
        lines.append("  );")
        lines.append("};")
        
        return lines
    
    def _generate_step_code(self, step, indent: str) -> List[str]:
        """Generate TypeScript code for a step."""
        code_lines = []
        step_id = step.node_id
        var_name = self.step_var[step_id]
        
        code_lines.append(f"{indent}// Step: {step_id} ({step.action})")
        
        if isinstance(step, IRControlFlow):
            # Generate control flow code
            control_type = step.control_type
            
            if control_type in ("if_node", "if"):
                # Generate if condition
                condition = step.inputs.get("condition")
                condition_expr = self._generate_expression(condition, indent)
                
                code_lines.append(f"{indent}let {var_name}: StepResult = {{ result: false }};")
                code_lines.append(f"{indent}if ({condition_expr}) {{")
                code_lines.append(f"{indent}  {var_name}.result = true;")
                
                then_branch = step.branches.get("then", [])
                if then_branch:
                    then_step = then_branch[0]
                    then_code = self._generate_step_code(then_step, indent + "  ")
                    code_lines.extend(then_code)
                
                code_lines.append(f"{indent}}} else {{")
                
                else_branch = step.branches.get("else", [])
                if else_branch:
                    else_step = else_branch[0]
                    else_code = self._generate_step_code(else_step, indent + "  ")
                    code_lines.extend(else_code)
                
                code_lines.append(f"{indent}}}")
            
            elif control_type == "switch":
                # Generate switch statement
                value = step.inputs.get("value")
                value_expr = self._generate_expression(value, indent)
                
                code_lines.append(f"{indent}const switchValue = {value_expr};")
                code_lines.append(f"{indent}let matchedCase: any = null;")
                code_lines.append(f"{indent}let {var_name}: StepResult = {{ matchedCase: null }};")
                
                # Process cases
                cases = step.branches.items()
                is_first_case = True
                
                for case_name, case_steps in cases:
                    if case_name.startswith("case_"):
                        case_val = case_name[5:]
                        
                        if is_first_case:
                            code_lines.append(f"{indent}if (switchValue === {repr(case_val)}) {{")
                            is_first_case = False
                        else:
                            code_lines.append(f"{indent}}} else if (switchValue === {repr(case_val)}) {{")
                            
                        code_lines.append(f"{indent}  matchedCase = {repr(case_val)};")
                        
                        if case_steps:
                            case_step = case_steps[0]
                            case_code = self._generate_step_code(case_step, indent + "  ")
                            code_lines.extend(case_code)
                    
                    elif case_name == "default":
                        code_lines.append(f"{indent}}} else {{")
                        code_lines.append(f"{indent}  matchedCase = 'default';")
                        
                        if case_steps:
                            default_step = case_steps[0]
                            default_code = self._generate_step_code(default_step, indent + "  ")
                            code_lines.extend(default_code)
                
                code_lines.append(f"{indent}}}")
                code_lines.append(f"{indent}{var_name}.matchedCase = matchedCase;")
            
            elif control_type in ("while_loop", "while"):
                # Generate while loop
                condition = step.inputs.get("condition")
                condition_expr = self._generate_expression(condition, indent)
                max_iterations = step.inputs.get("max_iterations", IRLiteral("lit_max", 100, "int"))
                max_iter_expr = self._generate_expression(max_iterations, indent)
                
                code_lines.append(f"{indent}let iterationCount = 0;")
                code_lines.append(f"{indent}const iterationResults: any[] = [];")
                code_lines.append(f"{indent}while ({condition_expr} && iterationCount < {max_iter_expr}) {{")
                code_lines.append(f"{indent}  iterationCount++;")
                code_lines.append(f"{indent}  const iterationResult: any = {{}};")
                
                body_steps = step.branches.get("body", [])
                for body_step in body_steps:
                    body_code = self._generate_step_code(body_step, indent + "  ")
                    code_lines.extend(body_code)
                    code_lines.append(f"{indent}  iterationResult['{body_step.node_id}'] = {self.step_var[body_step.node_id]};")
                
                code_lines.append(f"{indent}  iterationResults.push(iterationResult);")
                code_lines.append(f"{indent}}}")
                
                code_lines.append(f"{indent}const {var_name}: StepResult = {{")
                code_lines.append(f"{indent}  iterationsRun: iterationCount,")
                code_lines.append(f"{indent}  resultsPerIteration: iterationResults,")
                code_lines.append(f"{indent}  loopEndedNaturally: !{condition_expr}")
                code_lines.append(f"{indent}}};")
            
            elif control_type == "for_each":
                # Generate for-each loop
                list_input = step.inputs.get("list", IRLiteral("lit_list", [], "list"))
                list_expr = self._generate_expression(list_input, indent)
                iterator_name = step.inputs.get("iterator_name", IRLiteral("lit_iter", "item", "str"))
                iterator_expr = self._generate_expression(iterator_name, indent)
                
                code_lines.append(f"{indent}let iterationCount = 0;")
                code_lines.append(f"{indent}const iterationResults: any[] = [];")
                code_lines.append(f"{indent}const forEachList = {list_expr};")
                code_lines.append(f"{indent}for (let idx = 0; idx < forEachList.length; idx++) {{")
                code_lines.append(f"{indent}  const {iterator_expr}Value = forEachList[idx];")
                code_lines.append(f"{indent}  const {iterator_expr}Index = idx;")
                code_lines.append(f"{indent}  iterationCount++;")
                code_lines.append(f"{indent}  flowVariables[{iterator_expr}] = {iterator_expr}Value;")
                code_lines.append(f"{indent}  flowVariables[`${{iterator_expr}}_index`] = {iterator_expr}Index;")
                code_lines.append(f"{indent}  const iterationResult: any = {{")
                code_lines.append(f"{indent}    {iterator_expr}: {iterator_expr}Value,")
                code_lines.append(f"{indent}    _index: {iterator_expr}Index")
                code_lines.append(f"{indent}  }};")
                
                body_steps = step.branches.get("body", [])
                for body_step in body_steps:
                    body_code = self._generate_step_code(body_step, indent + "  ")
                    code_lines.extend(body_code)
                    code_lines.append(f"{indent}  iterationResult['{body_step.node_id}'] = {self.step_var[body_step.node_id]};")
                
                code_lines.append(f"{indent}  iterationResults.push(iterationResult);")
                code_lines.append(f"{indent}}}")
                
                code_lines.append(f"{indent}const {var_name}: StepResult = {{")
                code_lines.append(f"{indent}  iterationsCompleted: iterationCount,")
                code_lines.append(f"{indent}  resultsPerIteration: iterationResults")
                code_lines.append(f"{indent}}};")
            
            elif control_type in ("try_catch", "try"):
                # Generate try-catch block
                code_lines.append(f"{indent}let {var_name}: StepResult;")
                code_lines.append(f"{indent}try {{")
                
                try_steps = step.branches.get("try", [])
                for try_step in try_steps:
                    try_code = self._generate_step_code(try_step, indent + "  ")
                    code_lines.extend(try_code)
                
                code_lines.append(f"{indent}  {var_name} = {{ success: true, errorDetails: null }};")
                code_lines.append(f"{indent}}} catch (error) {{")
                code_lines.append(f"{indent}  {var_name} = {{")
                code_lines.append(f"{indent}    success: false,")
                code_lines.append(f"{indent}    errorDetails: {{ type: error.name, message: error.message }}")
                code_lines.append(f"{indent}  }};")
                code_lines.append(f"{indent}  flowVariables.__error = {{ type: error.name, message: error.message }};")
                
                catch_steps = step.branches.get("catch", [])
                for catch_step in catch_steps:
                    catch_code = self._generate_step_code(catch_step, indent + "  ")
                    code_lines.extend(catch_code)
                
                code_lines.append(f"{indent}  if ('__error' in flowVariables) {{")
                code_lines.append(f"{indent}    delete flowVariables.__error;")
                code_lines.append(f"{indent}  }}")
                code_lines.append(f"{indent}}}")
            
        else:
            # Generate regular step code
            if step.action.startswith("variables.") and step.action in (
                "variables.get_local", "variables.set_local", 
                "variables.get_env", "variables.get", "variables.set"
            ):
                # Generate native variable operations
                if step.action == "variables.get_local":
                    name_expr = self._generate_expression(step.inputs.get("name"), indent)
                    default_expr = self._generate_expression(step.inputs.get("default"), indent)
                    
                    code_lines.append(f"{indent}const {var_name}: StepResult = {{ value: flowVariables[{name_expr}] !== undefined ? flowVariables[{name_expr}] : {default_expr} }};")
                    
                elif step.action == "variables.set_local":
                    name_expr = self._generate_expression(step.inputs.get("name"), indent)
                    value_expr = self._generate_expression(step.inputs.get("value"), indent)
                    
                    code_lines.append(f"{indent}flowVariables[{name_expr}] = {value_expr};")
                    code_lines.append(f"{indent}const {var_name}: StepResult = {{ value: {value_expr} }};")
                    
                elif step.action == "variables.get_env":
                    name_expr = self._generate_expression(step.inputs.get("name"), indent)
                    default_expr = self._generate_expression(step.inputs.get("default"), indent)
                    
                    if self.output_type == "class":
                        code_lines.append(f"{indent}const {var_name}: StepResult = {{ value: this.getEnv({name_expr}, {default_expr}) }};")
                    elif self.output_type == "react":
                        code_lines.append(f"{indent}const {var_name}: StepResult = {{ value: getEnv({name_expr}, {default_expr}) }};")
                    else:
                        code_lines.append(f"{indent}const {var_name}: StepResult = {{ value: getEnv({name_expr}, {default_expr}) }};")
                    
                elif step.action == "variables.get":
                    name_expr = self._generate_expression(step.inputs.get("name"), indent)
                    default_expr = self._generate_expression(step.inputs.get("default"), indent)
                    
                    code_lines.append(f"{indent}let {var_name}: StepResult;")
                    code_lines.append(f"{indent}if ({name_expr} in flowVariables) {{")
                    code_lines.append(f"{indent}  {var_name} = {{ value: flowVariables[{name_expr}] }};")
                    code_lines.append(f"{indent}}} else {{")
                    
                    if self.output_type == "class":
                        code_lines.append(f"{indent}  {var_name} = {{ value: this.getEnv({name_expr}, {default_expr}) }};")
                    elif self.output_type == "react":
                        code_lines.append(f"{indent}  {var_name} = {{ value: getEnv({name_expr}, {default_expr}) }};")
                    else:
                        code_lines.append(f"{indent}  {var_name} = {{ value: getEnv({name_expr}, {default_expr}) }};")
                        
                    code_lines.append(f"{indent}}}")
                    
                elif step.action == "variables.set":
                    name_expr = self._generate_expression(step.inputs.get("name"), indent)
                    value_expr = self._generate_expression(step.inputs.get("value"), indent)
                    
                    code_lines.append(f"{indent}flowVariables[{name_expr}] = {value_expr};")
                    code_lines.append(f"{indent}const {var_name}: StepResult = {{ value: {value_expr} }};")
            else:
                # In TypeScript, we would typically need to implement or mock the actions
                # For now, we'll just generate a stub
                code_lines.append(f"{indent}// TODO: Implement action {step.action}")
                code_lines.append(f"{indent}const {var_name}: StepResult = {{ status: 'not_implemented' }};")
        
        return code_lines
    
    def _generate_expression(self, node, indent: str = "") -> str:
        """Generate a TypeScript expression from an IR node."""
        if node is None:
            return "null"
            
        if isinstance(node, IRLiteral):
            if node.value_type == "expression":
                # This is a raw expression
                return node.value
            elif node.value_type == "bool":
                # Special case for booleans to ensure correct casing
                return str(node.value).lower()
            else:
                # Regular literal
                return json.dumps(node.value)
                
        elif isinstance(node, IRVariableRef):
            if node.source_type == "env":
                if self.output_type == "class":
                    return f"this.getEnv('{node.source_name}', '')"
                elif self.output_type == "react":
                    return f"getEnv('{node.source_name}', '')"
                else:
                    return f"getEnv('{node.source_name}', '')"
                
            elif node.source_type == "flow_var":
                return f"flowVariables['{node.source_name}'] || null"
                
            elif node.source_type == "step":
                step_var = self.step_var.get(node.source_name, f"{node.source_name}Result")
                if node.field_path:
                    return f"{step_var}['{node.field_path}']"
                else:
                    return step_var
                    
        elif isinstance(node, IRTemplate):
            # Process template
            template_str = node.template
            processed_expr_map = {}
            interpolations = []
            
            # Process expressions and build interpolation mapping
            for i, expr in enumerate(node.expressions):
                expr_str = self._generate_expression(expr, indent)
                placeholder = f"__expr_{i}__"
                processed_expr_map[placeholder] = expr_str
                
                if isinstance(expr, IRVariableRef):
                    if expr.source_type == "env" and expr.source_name:
                        orig_placeholder = f"{{{{env.{expr.source_name}}}}}"
                        template_str = template_str.replace(orig_placeholder, placeholder)
                        
                    elif expr.source_type == "flow_var" and expr.source_name:
                        orig_placeholder1 = f"{{{{var.{expr.source_name}}}}}"
                        orig_placeholder2 = f"{{{{local.{expr.source_name}}}}}"
                        template_str = template_str.replace(orig_placeholder1, placeholder)
                        template_str = template_str.replace(orig_placeholder2, placeholder)
                        
                    elif expr.source_type == "step" and expr.source_name and expr.field_path:
                        orig_placeholder = f"{{{{{expr.source_name}.{expr.field_path}}}}}"
                        template_str = template_str.replace(orig_placeholder, placeholder)
            
            # Replace placeholders with interpolation expressions
            for placeholder, expr_str in processed_expr_map.items():
                template_str = template_str.replace(placeholder, "${" + expr_str + "}")
            
            # Fix any remaining double braces
            template_str = template_str.replace("{{", "{").replace("}}", "}")
            
            # Return as template literal
            return f"`{template_str}`"
        
        # Default fallback
        return JSON.stringify(str(node))

