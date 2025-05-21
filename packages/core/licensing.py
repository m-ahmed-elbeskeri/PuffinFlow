"""Licensing module for FlowForge."""

import os
from typing import Dict, Any, Optional

# Default configuration with OSS features enabled
DEFAULT_CONFIG = {
    "features": {
        # Core features (always available in OSS)
        "flow_execution": True,
        "core_integrations": True,
        "code_generation": True,
        
        # Enterprise/Cloud features (disabled by default)
        "rbac": False,
        "team_management": False,
        "audit_logging": False,
        "usage_quotas": False,
        "multi_tenancy": False,
        "billing_integration": False,
    }
}

# Global configuration
_config: Dict[str, Any] = {}

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from file or environment.
    
    Args:
        config_path: Optional path to config file
        
    Returns:
        Configuration dictionary
    """
    global _config
    
    # Start with default configuration
    _config = DEFAULT_CONFIG.copy()
    
    # Check for license file
    license_path = config_path or os.environ.get("FLOWFORGE_LICENSE_PATH")
    if license_path and os.path.exists(license_path):
        try:
            import yaml
            with open(license_path) as f:
                license_data = yaml.safe_load(f)
                
            if isinstance(license_data, dict) and "features" in license_data:
                _config["features"].update(license_data["features"])
        except Exception as e:
            print(f"Error loading license: {e}")
    
    # Check for environment variable overrides
    for feature in _config["features"]:
        env_var = f"FLOWFORGE_FEATURE_{feature.upper()}"
        if env_var in os.environ:
            value = os.environ[env_var].lower()
            _config["features"][feature] = value in ("1", "true", "yes", "on")
    
    return _config

def has_feature(name: str) -> bool:
    """
    Check if a feature is enabled in the current license.
    
    Args:
        name: Feature name
        
    Returns:
        True if feature is enabled, False otherwise
    """
    global _config
    
    # Load config if not already loaded
    if not _config:
        load_config()
    
    return _config.get("features", {}).get(name, False)

# Initialize configuration on module load
load_config()