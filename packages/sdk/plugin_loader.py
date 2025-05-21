"""Plugin loader for FlowForge integrations."""

from typing import Dict, List, Optional
import os
from pathlib import Path
from .plugin import Plugin

def load_plugins(path: str = "./integrations") -> Dict[str, Plugin]:
    """
    Load all plugins from a directory.
    
    Args:
        path: Path to plugins directory
        
    Returns:
        Dictionary of plugin name to Plugin instance
    """
    plugins = {}
    plugins_path = Path(path)
    
    if not plugins_path.exists() or not plugins_path.is_dir():
        print(f"Warning: Plugins directory '{path}' not found")
        return plugins
    
    # Scan for plugin directories
    for plugin_dir in plugins_path.iterdir():
        if plugin_dir.is_dir():
            manifest_path = plugin_dir / "manifest.yaml"
            
            if manifest_path.exists():
                # Load plugin
                plugin_name = plugin_dir.name
                plugin = Plugin(plugin_name, plugin_dir)
                plugin.load_actions()
                plugins[plugin_name] = plugin
                print(f"Loaded plugin: {plugin_name}")
    
    return plugins