"""Authentication module for Google Sheets integration."""

import os
import json
import pickle
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

# Required Google API libraries
try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    raise ImportError(
        "Google API libraries not installed. "
        "Run 'pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib'"
    )

# Cache for storing credentials
_credentials_cache = {}

def authenticate(credentials_json: str, scopes: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Authenticate with Google Sheets API using service account credentials.
    
    Args:
        credentials_json: Path to service account credentials JSON file or the JSON content itself
        scopes: OAuth scopes to request (default: ["https://www.googleapis.com/auth/spreadsheets"])
        
    Returns:
        Dict with credentials and success status
    """
    if scopes is None:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    
    # Generate a cache key
    cache_key = f"{credentials_json}:{','.join(scopes)}"
    
    # Check if we have cached credentials
    if cache_key in _credentials_cache:
        return {
            "credentials": _credentials_cache[cache_key],
            "success": True,
            "message": "Using cached credentials"
        }
    
    try:
        # Check if credentials_json is a file path
        credentials_path = Path(credentials_json)
        if credentials_path.exists() and credentials_path.is_file():
            # It's a file path, load the JSON
            with open(credentials_path, 'r') as f:
                creds_data = json.load(f)
        else:
            # Assume it's the JSON content as a string
            try:
                creds_data = json.loads(credentials_json)
            except json.JSONDecodeError:
                # If it's not valid JSON, check for environment variable
                if credentials_json.startswith('env.'):
                    env_var = credentials_json[4:]
                    if env_var in os.environ:
                        env_value = os.environ[env_var]
                        try:
                            creds_data = json.loads(env_value)
                        except json.JSONDecodeError:
                            # If the environment variable is not valid JSON, it might be a file path
                            env_path = Path(env_value)
                            if env_path.exists() and env_path.is_file():
                                with open(env_path, 'r') as f:
                                    creds_data = json.load(f)
                            else:
                                raise ValueError(f"Environment variable {env_var} does not contain valid JSON or a valid file path")
                    else:
                        raise ValueError(f"Environment variable {env_var} not found")
                else:
                    raise ValueError("Invalid credentials: not a valid file path or JSON string")
        
        # Create credentials from the JSON data
        credentials = service_account.Credentials.from_service_account_info(
            creds_data, scopes=scopes)
        
        # Cache the credentials
        _credentials_cache[cache_key] = credentials
        
        return {
            "credentials": credentials,
            "success": True,
            "message": "Successfully authenticated with service account"
        }
        
    except Exception as e:
        # Handle OAuth2 client flow as fallback (for user account authentication)
        try:
            # Check if this might be OAuth client ID credentials instead of service account
            if isinstance(creds_data, dict) and 'installed' in creds_data:
                flow = InstalledAppFlow.from_client_config(creds_data, scopes)
                credentials = flow.run_local_server(port=0)
                
                # Cache the credentials
                _credentials_cache[cache_key] = credentials
                
                return {
                    "credentials": credentials,
                    "success": True,
                    "message": "Successfully authenticated with OAuth2 flow"
                }
        except Exception as oauth_error:
            return {
                "credentials": None,
                "success": False,
                "error": str(e),
                "message": f"Authentication failed: {str(e)}. OAuth fallback error: {str(oauth_error)}"
            }
            
        return {
            "credentials": None,
            "success": False,
            "error": str(e),
            "message": f"Authentication failed: {str(e)}"
        }

def get_sheets_service(credentials: Any) -> Any:
    """
    Get the Google Sheets API service using the provided credentials.
    
    Args:
        credentials: Authorized Google credentials
        
    Returns:
        Google Sheets API service
    """
    return build('sheets', 'v4', credentials=credentials)

def get_drive_service(credentials: Any) -> Any:
    """
    Get the Google Drive API service using the provided credentials.
    
    Args:
        credentials: Authorized Google credentials
        
    Returns:
        Google Drive API service
    """
    return build('drive', 'v3', credentials=credentials)