"""Simplified integration handler that copies existing integration files."""

import os
import yaml
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

class IntegrationHandler:
    """
    Simplified integration handler that discovers and copies existing integration files.
    No stub generation - just works with what actually exists.
    """
    
    def __init__(self, integrations_dir: str = "./integrations"):
        """
        Initialize the integration handler.
        
        Args:
            integrations_dir: Path to the integrations directory
        """
        self.integrations_dir = Path(integrations_dir)
        self.manifests: Dict[str, Dict[str, Any]] = {}
        self.integration_files: Dict[str, List[Path]] = {}
        self.requirements_cache: Dict[str, Set[str]] = {}
        
        # Discover what actually exists
        self._discover_integrations()
        
    def _discover_integrations(self):
        """Discover all integrations and their actual files."""
        if not self.integrations_dir.exists():
            print(f"Integrations directory not found: {self.integrations_dir}")
            return
            
        for integration_dir in self.integrations_dir.iterdir():
            if not integration_dir.is_dir():
                continue
                
            integration_name = integration_dir.name
            
            # Find all Python files in the integration
            python_files = list(integration_dir.glob("*.py"))
            if python_files:
                self.integration_files[integration_name] = python_files
            
            # Load manifest if it exists
            manifest_path = integration_dir / "manifest.yaml"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r") as f:
                        self.manifests[integration_name] = yaml.safe_load(f)
                except Exception as e:
                    print(f"Error loading manifest for {integration_name}: {e}")
            
            # Load requirements if they exist
            self._load_requirements(integration_name, integration_dir)
    
    def _load_requirements(self, integration_name: str, integration_dir: Path):
        """Load requirements from requirements.txt if it exists."""
        requirements = set()
        
        req_file = integration_dir / "requirements.txt"
        if req_file.exists():
            try:
                with open(req_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            requirements.add(line)
            except Exception as e:
                print(f"Error loading requirements for {integration_name}: {e}")
        
        # Also check manifest for requirements
        manifest = self.manifests.get(integration_name, {})
        manifest_reqs = manifest.get('requirements', [])
        if isinstance(manifest_reqs, list):
            requirements.update(manifest_reqs)
        
        if requirements:
            self.requirements_cache[integration_name] = requirements
    
    def get_import_statements(self, integration_name: str, language: str) -> List[str]:
        """Get import statements based on actual files that exist."""
        if language != "python":
            return []  # Only handle Python for now
        
        if integration_name not in self.integration_files:
            return []
        
        imports = []
        python_files = self.integration_files[integration_name]
        
        # Get module names from actual files (excluding __init__.py)
        modules = []
        for file_path in python_files:
            if file_path.name != "__init__.py":
                module_name = file_path.stem
                modules.append(module_name)
        
        # Generate imports based on what actually exists
        if modules:
            # Import specific modules
            for module in sorted(modules):
                imports.append(f"from integrations.{integration_name} import {module}")
        else:
            # Fallback to importing the integration package
            imports.append(f"import integrations.{integration_name}")
        
        return imports
    
    def get_function_call(self, integration_name: str, action_name: str, language: str) -> Optional[str]:
        """Get function call based on manifest or infer from file structure."""
        if language != "python":
            return None
        
        # Check manifest first
        manifest = self.manifests.get(integration_name, {})
        actions = manifest.get('actions', {})
        action_def = actions.get(action_name, {})
        implementation = action_def.get('implementation')
        
        if implementation:
            # Use the implementation defined in manifest
            return implementation
        
        # Infer from file structure
        if integration_name in self.integration_files:
            python_files = self.integration_files[integration_name]
            
            # Look for a file that might contain this action
            for file_path in python_files:
                module_name = file_path.stem
                if module_name == action_name or action_name.startswith(module_name):
                    return f"{module_name}.{action_name}"
            
            # Default: assume first module or action name
            if python_files:
                first_module = python_files[0].stem
                if first_module != "__init__":
                    return f"{first_module}.{action_name}"
        
        # Final fallback
        return f"{action_name}.{action_name}"
    
    def copy_integration_files(self, integration_name: str, target_dir: Path) -> bool:
        """Copy all files for an integration to the target directory."""
        if integration_name not in self.integration_files:
            print(f"Integration '{integration_name}' not found")
            return False
        
        integration_target_dir = target_dir / integration_name
        integration_target_dir.mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py
        (integration_target_dir / "__init__.py").write_text('"""FlowForge integration."""\n')
        
        # Copy all Python files
        python_files = self.integration_files[integration_name]
        copied_count = 0
        
        for source_file in python_files:
            if source_file.name == "__init__.py":
                continue  # Skip, we create our own
            
            target_file = integration_target_dir / source_file.name
            try:
                shutil.copy2(source_file, target_file)
                copied_count += 1
            except Exception as e:
                print(f"Error copying {source_file.name} for {integration_name}: {e}")
        
        print(f"Copied {copied_count} files for integration '{integration_name}'")
        return copied_count > 0
    
    def get_integration_requirements(self, integration_name: str) -> Set[str]:
        """Get requirements for an integration."""
        return self.requirements_cache.get(integration_name, set()).copy()
    
    def get_available_integrations(self) -> List[str]:
        """Get list of all available integrations."""
        return list(self.integration_files.keys())
    
    def get_integration_info(self, integration_name: str) -> Optional[Dict[str, Any]]:
        """Get information about an integration."""
        if integration_name not in self.integration_files:
            return None
        
        info = {
            'name': integration_name,
            'files': [f.name for f in self.integration_files[integration_name]],
            'requirements': list(self.get_integration_requirements(integration_name))
        }
        
        # Add manifest info if available
        if integration_name in self.manifests:
            manifest = self.manifests[integration_name]
            info.update({
                'description': manifest.get('description', ''),
                'version': manifest.get('version', '1.0.0'),
                'actions': list(manifest.get('actions', {}).keys())
            })
        
        return info
    
    def get_action_info(self, integration_name: str, action_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific action."""
        manifest = self.manifests.get(integration_name)
        if not manifest:
            return None
        
        actions = manifest.get('actions', {})
        return actions.get(action_name)
    
    def integration_exists(self, integration_name: str) -> bool:
        """Check if an integration exists."""
        return integration_name in self.integration_files
    
    def list_integration_files(self, integration_name: str) -> List[str]:
        """List all files for an integration."""
        if integration_name not in self.integration_files:
            return []
        
        return [f.name for f in self.integration_files[integration_name]]
    
    def get_integration_path(self, integration_name: str) -> Optional[Path]:
        """Get the path to an integration directory."""
        integration_path = self.integrations_dir / integration_name
        if integration_path.exists() and integration_path.is_dir():
            return integration_path
        return None