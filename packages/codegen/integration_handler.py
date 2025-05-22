"""Handles integration-specific code generation across languages."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

class IntegrationHandler:
    """
    Handles integration-specific code generation for multiple languages.
    This class manages loading integration manifests and providing language-specific
    implementation details for code generators.
    """
    
    def __init__(self, integrations_dir: str = "./integrations"):
        """
        Initialize the integration handler.
        
        Args:
            integrations_dir: Path to the integrations directory
        """
        self.integrations_dir = Path(integrations_dir)
        self.manifests: Dict[str, Dict[str, Any]] = {}
        self.language_implementations: Dict[str, Dict[str, Dict[str, str]]] = {
            "python": {},
            "typescript": {},
            "javascript": {}
        }
        
        # Load manifests
        self._load_manifests()
        
    def _load_manifests(self):
        """Load all integration manifests from the integrations directory."""
        if not self.integrations_dir.exists():
            print(f"Integrations directory not found: {self.integrations_dir}")
            return
            
        for integration_dir in self.integrations_dir.iterdir():
            if not integration_dir.is_dir():
                continue
                
            # Look for manifest.yaml
            manifest_path = integration_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue
                
            try:
                with open(manifest_path, "r") as f:
                    manifest = yaml.safe_load(f)
                    
                # Store the manifest
                integration_name = manifest.get("name") or integration_dir.name
                self.manifests[integration_name] = manifest
                
                # Extract language-specific implementations
                self._extract_implementations(integration_name, manifest)
                
            except Exception as e:
                print(f"Error loading manifest for integration {integration_dir.name}: {e}")
    
    def _extract_implementations(self, integration_name: str, manifest: Dict[str, Any]):
        """
        Extract language-specific implementations from a manifest.
        
        Args:
            integration_name: Name of the integration
            manifest: Integration manifest dictionary
        """
        # Top-level implementations
        implementations = manifest.get("implementations", {})
        for language, implementation in implementations.items():
            if language in self.language_implementations:
                self.language_implementations[language][integration_name] = {
                    "__default__": implementation
                }
        
        # Action-specific implementations
        for action_name, action_def in manifest.get("actions", {}).items():
            action_implementations = action_def.get("implementations", {})
            
            for language, implementation in action_implementations.items():
                if language in self.language_implementations:
                    if integration_name not in self.language_implementations[language]:
                        self.language_implementations[language][integration_name] = {}
                        
                    self.language_implementations[language][integration_name][action_name] = implementation
                    
            # If no language-specific implementation, use the default
            default_impl = action_def.get("implementation")
            if default_impl:
                for language in self.language_implementations:
                    if integration_name in self.language_implementations[language]:
                        if action_name not in self.language_implementations[language][integration_name]:
                            self.language_implementations[language][integration_name][action_name] = default_impl
    
    def get_import_statements(self, integration_name: str, language: str) -> List[str]:
        """
        Get import statements for an integration in the specified language.
        
        Args:
            integration_name: Name of the integration
            language: Target language (python, typescript, etc.)
            
        Returns:
            List of import statements
        """
        if language not in self.language_implementations:
            return []
            
        if integration_name not in self.language_implementations[language]:
            return []
            
        # Get default implementation module
        default_impl = self.language_implementations[language][integration_name].get("__default__")
        
        if language == "python":
            if default_impl:
                if "." in default_impl:
                    module, _ = default_impl.split(".", 1)
                    return [f"from integrations.{integration_name} import {module}"]
                else:
                    return [f"from integrations.{integration_name} import {default_impl}"]
            else:
                # Find modules from manifest
                manifest = self.manifests.get(integration_name, {})
                modules = manifest.get("modules", [])
                if modules:
                    return [f"from integrations.{integration_name} import {module}" for module in modules]
        
        elif language == "typescript" or language == "javascript":
            if default_impl:
                return [f"import {{{default_impl.split('.')[0]}}} from './integrations/{integration_name}';"]
            else:
                # Just import the integration
                capitalized = integration_name.capitalize()
                return [f"import {{{capitalized}}} from './integrations/{integration_name}';"]
                
        return []
    
    def get_function_call(self, integration_name: str, action_name: str, language: str) -> Optional[str]:
        """
        Get the function call expression for an action in the specified language.
        
        Args:
            integration_name: Name of the integration
            action_name: Name of the action
            language: Target language (python, typescript, etc.)
            
        Returns:
            Function call expression or None if not found
        """
        if language not in self.language_implementations:
            return None
            
        if integration_name not in self.language_implementations[language]:
            return None
            
        # Try to get action-specific implementation
        implementation = self.language_implementations[language][integration_name].get(action_name)
        
        # If not found, try the default
        if not implementation:
            implementation = self.language_implementations[language][integration_name].get("__default__")
            
            if implementation:
                if "." in implementation:
                    module, func = implementation.split(".", 1)
                    implementation = f"{module}.{action_name}"
                else:
                    implementation = f"{implementation}.{action_name}"
        
        if not implementation:
            # Try to construct a reasonable default
            if language == "python":
                # Convert to module.function format
                if "_" in action_name:
                    module = action_name.split("_")[0]
                    return f"{module}.{action_name}"
                else:
                    # Just use the action name as module name
                    return f"{action_name}.{action_name}"
            
            elif language == "typescript" or language == "javascript":
                # Use camelCase
                capitalized = integration_name.capitalize()
                return f"{capitalized}.{action_name}"
        
        return implementation
    
    def get_integration_info(self, integration_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an integration.
        
        Args:
            integration_name: Name of the integration
            
        Returns:
            Integration information or None if not found
        """
        return self.manifests.get(integration_name)
    
    def get_action_info(self, integration_name: str, action_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an action.
        
        Args:
            integration_name: Name of the integration
            action_name: Name of the action
            
        Returns:
            Action information or None if not found
        """
        integration = self.manifests.get(integration_name)
        if not integration:
            return None
            
        actions = integration.get("actions", {})
        return actions.get(action_name)
    
    def create_language_implementation(self, integration_name: str, language: str, output_dir: Optional[Path] = None) -> str:
        """
        Create a language-specific implementation for an integration.
        
        Args:
            integration_name: Name of the integration
            language: Target language (python, typescript, etc.)
            output_dir: Optional directory to write implementation file
            
        Returns:
            Generated implementation code
        """
        integration = self.manifests.get(integration_name)
        if not integration:
            return f"// Integration {integration_name} not found"
            
        actions = integration.get("actions", {})
        
        code_lines = []
        
        if language == "python":
            # Generate Python implementation
            code_lines.append(f'"""{integration.get("description", f"{integration_name} integration")}"""')
            code_lines.append("")
            
            # Add imports
            code_lines.append("import os")
            
            # Special-case common integrations
            if integration_name == "http" or integration_name == "https":
                code_lines.append("import requests")
            elif integration_name == "file" or integration_name == "fs":
                code_lines.append("import os.path")
                code_lines.append("import json")
            
            code_lines.append("")
            
            # Generate functions for each action
            for action_name, action_def in actions.items():
                description = action_def.get("description", f"Execute {action_name}")
                inputs = action_def.get("inputs", {})
                outputs = action_def.get("outputs", {})
                
                # Generate function parameters
                params = []
                for input_name, input_def in inputs.items():
                    if isinstance(input_def, dict):
                        default = input_def.get("default")
                        if default is not None:
                            params.append(f"{input_name}={repr(default)}")
                        elif not input_def.get("required", False):
                            params.append(f"{input_name}=None")
                        else:
                            params.append(input_name)
                    else:
                        params.append(f"{input_name}=None")
                
                code_lines.append(f"def {action_name}({', '.join(params)}):")
                code_lines.append(f'    """{description}"""')
                
                # Special-case common integrations
                if integration_name == "http" and action_name == "get":
                    code_lines.append("    response = requests.get(url, headers=headers, params=params, timeout=timeout)")
                    code_lines.append("    return {")
                    code_lines.append('        "status": response.status_code,')
                    code_lines.append('        "body": response.text,')
                    code_lines.append('        "headers": dict(response.headers)')
                    code_lines.append("    }")
                    
                elif integration_name == "file" and action_name == "read":
                    code_lines.append("    try:")
                    code_lines.append("        with open(path, 'r') as f:")
                    code_lines.append("            content = f.read()")
                    code_lines.append("        return {'content': content}")
                    code_lines.append("    except Exception as e:")
                    code_lines.append("        return {'error': str(e)}")
                    
                else:
                    # Generic implementation
                    if outputs:
                        output_dict = ", ".join([f'"{name}": None' for name in outputs])
                        code_lines.append(f"    return {{{output_dict}}}")
                    else:
                        code_lines.append('    return {"status": "success"}')
                
                code_lines.append("")
                
        elif language == "typescript":
            # Generate TypeScript implementation
            code_lines.append(f'/**')
            code_lines.append(f' * {integration.get("description", f"{integration_name} integration")}')
            code_lines.append(f' */')
            code_lines.append("")
            
            # Special-case common integrations
            if integration_name == "http" or integration_name == "https":
                code_lines.append("// HTTP client implementation")
            elif integration_name == "file" or integration_name == "fs":
                code_lines.append("// File system implementation")
            
            code_lines.append("")
            
            # Export namespace/class
            capitalized = integration_name.capitalize()
            code_lines.append(f"export namespace {capitalized} {{")
            
            # Generate functions for each action
            for action_name, action_def in actions.items():
                description = action_def.get("description", f"Execute {action_name}")
                inputs = action_def.get("inputs", {})
                outputs = action_def.get("outputs", {})
                
                # Generate function parameters with types
                params = []
                for input_name, input_def in inputs.items():
                    if isinstance(input_def, dict):
                        input_type = self._map_type_to_typescript(input_def.get("type", "any"))
                        if input_def.get("required", False):
                            params.append(f"{input_name}: {input_type}")
                        else:
                            params.append(f"{input_name}?: {input_type}")
                    else:
                        params.append(f"{input_name}: any")
                
                # Generate return type
                return_type = "any"
                if outputs:
                    output_types = []
                    for output_name, output_def in outputs.items():
                        if isinstance(output_def, dict):
                            output_type = self._map_type_to_typescript(output_def.get("type", "any"))
                            output_types.append(f"{output_name}: {output_type}")
                        else:
                            output_type = self._map_type_to_typescript(output_def)
                            output_types.append(f"{output_name}: {output_type}")
                    
                    return_type = f"{{ {', '.join(output_types)} }}"
                
                code_lines.append(f"  /**")
                code_lines.append(f"   * {description}")
                code_lines.append(f"   */")
                code_lines.append(f"  export async function {action_name}({', '.join(params)}): Promise<{return_type}> {{")
                
                # Special-case common integrations
                if integration_name == "http" and action_name == "get":
                    code_lines.append("    const urlObj = new URL(url);")
                    code_lines.append("    ")
                    code_lines.append("    // Add query parameters")
                    code_lines.append("    if (params) {")
                    code_lines.append("      Object.entries(params).forEach(([key, value]) => {")
                    code_lines.append("        urlObj.searchParams.append(key, value.toString());")
                    code_lines.append("      });")
                    code_lines.append("    }")
                    code_lines.append("    ")
                    code_lines.append("    // Set timeout")
                    code_lines.append("    const controller = new AbortController();")
                    code_lines.append("    const timeoutId = setTimeout(() => controller.abort(), timeout || 30000);")
                    code_lines.append("    ")
                    code_lines.append("    try {")
                    code_lines.append("      const response = await fetch(urlObj.toString(), {")
                    code_lines.append("        method: 'GET',")
                    code_lines.append("        headers: headers || {},")
                    code_lines.append("        signal: controller.signal")
                    code_lines.append("      });")
                    code_lines.append("      ")
                    code_lines.append("      return {")
                    code_lines.append("        status: response.status,")
                    code_lines.append("        body: await response.text(),")
                    code_lines.append("        headers: Object.fromEntries(response.headers.entries())")
                    code_lines.append("      };")
                    code_lines.append("    } finally {")
                    code_lines.append("      clearTimeout(timeoutId);")
                    code_lines.append("    }")
                elif integration_name == "file" and action_name == "read":
                    code_lines.append("    // Note: In browser environments, file operations require special handling")
                    code_lines.append("    if (typeof window !== 'undefined' && window.fs) {")
                    code_lines.append("      // Use browser fs API if available")
                    code_lines.append("      try {")
                    code_lines.append("        const content = await window.fs.readFile(path, { encoding: 'utf8' });")
                    code_lines.append("        return { content };")
                    code_lines.append("      } catch (e) {")
                    code_lines.append("        return { error: e.message };")
                    code_lines.append("      }")
                    code_lines.append("    } else if (typeof require !== 'undefined') {")
                    code_lines.append("      // Node.js environment")
                    code_lines.append("      try {")
                    code_lines.append("        const fs = require('fs').promises;")
                    code_lines.append("        const content = await fs.readFile(path, 'utf8');")
                    code_lines.append("        return { content };")
                    code_lines.append("      } catch (e) {")
                    code_lines.append("        return { error: e.message };")
                    code_lines.append("      }")
                    code_lines.append("    } else {")
                    code_lines.append("      return { error: 'File system not available in this environment' };")
                    code_lines.append("    }")
                else:
                    # Generate a stub implementation
                    if outputs:
                        output_dict = ", ".join([f'{name}: null' for name in outputs])
                        code_lines.append(f"    // TODO: Implement {action_name}")
                        code_lines.append(f"    return {{ {output_dict} }};")
                    else:
                        code_lines.append('    // TODO: Implement {action_name}')
                        code_lines.append('    return { status: "success" };')
                
                code_lines.append("  }")
                code_lines.append("")
            
            code_lines.append("}")
            
        elif language == "javascript":
            # Generate JavaScript implementation similar to TypeScript but without types
            code_lines.append(f'/**')
            code_lines.append(f' * {integration.get("description", f"{integration_name} integration")}')
            code_lines.append(f' */')
            code_lines.append("")
            
            # Export namespace/object
            code_lines.append(f"export const {integration_name} = {{")
            
            # Generate functions for each action
            for i, (action_name, action_def) in enumerate(actions.items()):
                description = action_def.get("description", f"Execute {action_name}")
                inputs = action_def.get("inputs", {})
                
                # Generate function parameters
                params = []
                for input_name, input_def in inputs.items():
                    params.append(input_name)
                
                code_lines.append(f"  /**")
                code_lines.append(f"   * {description}")
                code_lines.append(f"   */")
                code_lines.append(f"  {action_name}: async function({', '.join(params)}) {{")
                
                # Special-case common integrations (similar to TypeScript)
                if integration_name == "http" and action_name == "get":
                    code_lines.append("    const urlObj = new URL(url);")
                    code_lines.append("    ")
                    code_lines.append("    // Add query parameters")
                    code_lines.append("    if (params) {")
                    code_lines.append("      Object.entries(params).forEach(([key, value]) => {")
                    code_lines.append("        urlObj.searchParams.append(key, value.toString());")
                    code_lines.append("      });")
                    code_lines.append("    }")
                    code_lines.append("    ")
                    code_lines.append("    // Set timeout")
                    code_lines.append("    const controller = new AbortController();")
                    code_lines.append("    const timeoutId = setTimeout(() => controller.abort(), timeout || 30000);")
                    code_lines.append("    ")
                    code_lines.append("    try {")
                    code_lines.append("      const response = await fetch(urlObj.toString(), {")
                    code_lines.append("        method: 'GET',")
                    code_lines.append("        headers: headers || {},")
                    code_lines.append("        signal: controller.signal")
                    code_lines.append("      });")
                    code_lines.append("      ")
                    code_lines.append("      return {")
                    code_lines.append("        status: response.status,")
                    code_lines.append("        body: await response.text(),")
                    code_lines.append("        headers: Object.fromEntries(response.headers.entries())")
                    code_lines.append("      };")
                    code_lines.append("    } finally {")
                    code_lines.append("      clearTimeout(timeoutId);")
                    code_lines.append("    }")
                else:
                    # Generate a stub implementation
                    outputs = action_def.get("outputs", {})
                    if outputs:
                        output_dict = ", ".join([f'{name}: null' for name in outputs])
                        code_lines.append(f"    // TODO: Implement {action_name}")
                        code_lines.append(f"    return {{ {output_dict} }};")
                    else:
                        code_lines.append('    // TODO: Implement {action_name}')
                        code_lines.append('    return { status: "success" };')
                
                # Add comma for all but the last entry
                code_lines.append("  }" + ("," if i < len(actions) - 1 else ""))
                code_lines.append("")
            
            code_lines.append("};")
            
        # Write to file if output_dir is provided
        if output_dir is not None:
            os.makedirs(output_dir, exist_ok=True)
            
            # Determine file extension
            extension = {
                "python": ".py",
                "typescript": ".ts",
                "javascript": ".js"
            }.get(language, ".txt")
            
            filename = integration_name
            # For TypeScript/JavaScript, use index.ts/js
            if language in ("typescript", "javascript"):
                filename = "index"
                
            with open(output_dir / f"{filename}{extension}", "w") as f:
                f.write("\n".join(code_lines))
        
        return "\n".join(code_lines)
    
    def _map_type_to_typescript(self, type_str: str) -> str:
        """
        Map a type string to TypeScript type.
        
        Args:
            type_str: Type string from manifest
            
        Returns:
            TypeScript type
        """
        if not type_str or type_str == "any":
            return "any"
            
        type_map = {
            "string": "string",
            "number": "number",
            "boolean": "boolean",
            "array": "any[]",
            "object": "Record<string, any>",
            "integer": "number",
            "float": "number",
            "dict": "Record<string, any>",
            "list": "any[]"
        }
        
        # Handle array types like List[str]
        if type_str.startswith("List[") or type_str.startswith("Array["):
            inner_type = type_str[5:-1]
            ts_inner_type = self._map_type_to_typescript(inner_type)
            return f"{ts_inner_type}[]"
            
        # Handle dictionary types like Dict[str, any]
        if type_str.startswith("Dict[") or type_str.startswith("Map["):
            try:
                inner_types = type_str[5:-1].split(",")
                key_type = inner_types[0].strip()
                
                # TypeScript only allows string, number, or symbol as keys
                if key_type != "string" and key_type != "str":
                    # For simplicity, we default to string keys
                    return "Record<string, any>"
                    
                if len(inner_types) > 1:
                    value_type = inner_types[1].strip()
                    ts_value_type = self._map_type_to_typescript(value_type)
                    return f"Record<string, {ts_value_type}>"
            except:
                pass
                
            return "Record<string, any>"
        
        return type_map.get(type_str.lower(), "any")