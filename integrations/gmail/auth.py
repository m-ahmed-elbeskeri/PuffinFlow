"""OAuth authentication handling for Gmail integration."""

import os
import pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Configuration paths
CONFIG_DIR = Path.home() / ".flowforge" / "gmail"
TOKENS_FILE = CONFIG_DIR / "token.pickle"
CREDS_FILE = CONFIG_DIR / "credentials.json"

# Ensure config directory exists
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def setup_oauth(client_id, client_secret, redirect_uri="http://localhost:8080", 
                scopes=None):
    """
    Set up OAuth authentication for Gmail.
    
    Args:
        client_id: OAuth client ID from Google Cloud Platform
        client_secret: OAuth client secret from Google Cloud Platform
        redirect_uri: OAuth redirect URI
        scopes: List of OAuth scopes required
        
    Returns:
        Dictionary with auth_url and success status
    """
    try:
        if scopes is None:
            scopes = ["https://mail.google.com/"]
        elif isinstance(scopes, str):
            scopes = [scopes]
        
        # Create credentials.json file
        creds_data = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        
        import json
        with open(CREDS_FILE, 'w') as f:
            json.dump(creds_data, f)
        
        # Create OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDS_FILE,
            scopes=scopes,
            redirect_uri=redirect_uri
        )
        
        # Generate authorization URL
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        return {
            'auth_url': auth_url,
            'success': True,
            'message': 'Please open the auth_url in a browser and authorize the application'
        }
        
    except Exception as e:
        return {
            'auth_url': '',
            'success': False,
            'message': f'Error setting up OAuth: {str(e)}'
        }

def complete_oauth(auth_code):
    """
    Complete OAuth flow with authorization code.
    
    Args:
        auth_code: Authorization code from OAuth redirect
        
    Returns:
        Dictionary with success status and token info
    """
    try:
        if not CREDS_FILE.exists():
            return {
                'success': False,
                'message': 'No credentials file found. Please run setup_oauth first.'
            }
        
        # Create flow from credentials file
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDS_FILE,
            scopes=["https://mail.google.com/"]
        )
        
        # Exchange authorization code for access tokens
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        
        # Save credentials to file
        with open(TOKENS_FILE, 'wb') as token:
            pickle.dump(creds, token)
        
        # Return success
        token_info = {
            'access_token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'expiry': creds.expiry.isoformat() if creds.expiry else None
        }
        
        return {
            'success': True,
            'token_info': token_info,
            'message': 'Authentication successful. Token saved.'
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Error completing OAuth: {str(e)}'
        }

def refresh_token():
    """
    Refresh the OAuth token if expired.
    
    Returns:
        Dictionary with success status
    """
    try:
        if not TOKENS_FILE.exists():
            return {
                'success': False,
                'message': 'No token file found. Please complete OAuth flow first.'
            }
        
        # Load credentials
        with open(TOKENS_FILE, 'rb') as token:
            creds = pickle.load(token)
        
        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            
            # Save refreshed credentials
            with open(TOKENS_FILE, 'wb') as token:
                pickle.dump(creds, token)
            
            return {
                'success': True,
                'message': 'Token refreshed successfully'
            }
        elif creds and not creds.expired:
            return {
                'success': True,
                'message': 'Token is still valid'
            }
        else:
            return {
                'success': False,
                'message': 'Token cannot be refreshed. Please complete OAuth flow again.'
            }
            
    except Exception as e:
        return {
            'success': False,
            'message': f'Error refreshing token: {str(e)}'
        }