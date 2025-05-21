"""Secrets management for FlowForge with support for various backends."""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

# Default configuration
DEFAULT_CONFIG = {
    "secrets_file": "/secrets/secrets.json",
    "vault_enabled": False,
    "vault_url": None,
    "vault_token": None,
    "vault_path": "secret/data/flowforge",
    "doppler_token": None,
}

# Global configuration
_config: Dict[str, Any] = {}
_config.update(DEFAULT_CONFIG)

# Cache for secrets
_secrets_cache = {}
_workspace_secrets_cache = {}

def get_secret(name: str, default: Any = None) -> Any:
    """
    Get a secret by name from multiple possible sources.
    
    Args:
        name: Secret name
        default: Default value if not found
        
    Returns:
        The secret value
    """
    # Check cache first
    if name in _secrets_cache:
        return _secrets_cache[name]
    
    # 1. Try environment variable
    value = os.environ.get(name)
    if value is not None:
        _secrets_cache[name] = value
        return value
    
    # 2. Try mounted secrets file
    secrets_file = _config.get("secrets_file")
    if secrets_file:
        try:
            with open(secrets_file, "r") as f:
                secrets = json.load(f)
                if name in secrets:
                    value = secrets[name]
                    _secrets_cache[name] = value
                    return value
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    
    # 3. Try Vault if configured
    if _config.get("vault_enabled"):
        try:
            value = _get_from_vault(name)
            if value is not None:
                _secrets_cache[name] = value
                return value
        except Exception:
            pass
    
    # Return default if not found
    return default

def get_workspace_secret(workspace_id: str, name: str, default: Any = None) -> Any:
    """
    Get a workspace/tenant-specific secret.
    
    Args:
        workspace_id: Workspace/tenant ID
        name: Secret name
        default: Default value if not found
        
    Returns:
        The secret value
    """
    cache_key = f"{workspace_id}:{name}"
    
    # Check cache first
    if cache_key in _workspace_secrets_cache:
        return _workspace_secrets_cache[cache_key]
    
    # Try environment variable with workspace prefix
    env_key = f"{workspace_id}_{name}"
    value = os.environ.get(env_key)
    if value is not None:
        _workspace_secrets_cache[cache_key] = value
        return value
    
    # Try mounted workspace secrets file
    workspace_file = f"/secrets/{workspace_id}/secrets.json"
    try:
        with open(workspace_file, "r") as f:
            secrets = json.load(f)
            if name in secrets:
                value = secrets[name]
                _workspace_secrets_cache[cache_key] = value
                return value
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    # Try Vault if configured
    if _config.get("vault_enabled"):
        try:
            vault_path = f"secret/data/flowforge/{workspace_id}"
            value = _get_from_vault(name, vault_path)
            if value is not None:
                _workspace_secrets_cache[cache_key] = value
                return value
        except Exception:
            pass
    
    # Return default if not found
    return default

def _get_from_vault(name: str, path: Optional[str] = None) -> Optional[Any]:
    """Get a secret from HashiCorp Vault."""
    try:
        import hvac
    except ImportError:
        return None
    
    vault_url = _config.get("vault_url")
    vault_token = _config.get("vault_token")
    
    if not vault_url or not vault_token:
        return None
    
    client = hvac.Client(url=vault_url, token=vault_token)
    if not client.is_authenticated():
        return None
    
    vault_path = path or _config.get("vault_path")
    try:
        response = client.secrets.kv.v2.read_secret_version(path=vault_path)
        return response.get("data", {}).get("data", {}).get(name)
    except Exception:
        return None

def init_from_env() -> None:
    """Initialize configuration from environment variables."""
    if "SECRETS_FILE" in os.environ:
        _config["secrets_file"] = os.environ["SECRETS_FILE"]
    
    if "VAULT_ADDR" in os.environ and "VAULT_TOKEN" in os.environ:
        _config["vault_enabled"] = True
        _config["vault_url"] = os.environ["VAULT_ADDR"]
        _config["vault_token"] = os.environ["VAULT_TOKEN"]
        if "VAULT_PATH" in os.environ:
            _config["vault_path"] = os.environ["VAULT_PATH"]
    
    if "DOPPLER_TOKEN" in os.environ:
        _config["doppler_token"] = os.environ["DOPPLER_TOKEN"]

# Initialize from environment variables on module load
init_from_env()