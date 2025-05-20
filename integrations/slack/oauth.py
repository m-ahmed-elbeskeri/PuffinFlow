"""Implementation of Slack OAuth authentication."""

import requests
import json

def authorize(client_id, client_secret, code, redirect_uri=None):
    """
    Complete OAuth authorization flow with Slack.
    
    Args:
        client_id: Slack app client ID
        client_secret: Slack app client secret
        code: OAuth authorization code
        redirect_uri: OAuth redirect URI (optional)
        
    Returns:
        Dictionary with access token and team information
    """
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code
    }
    
    if redirect_uri:
        payload["redirect_uri"] = redirect_uri
    
    response = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data=payload
    )
    
    if response.status_code != 200:
        raise ValueError(f"Error completing OAuth: {response.text}")
    
    data = response.json()
    if not data.get("ok"):
        raise ValueError(f"Error from Slack API: {data.get('error')}")
    
    return {
        "access_token": data.get("access_token", ""),
        "team_id": data.get("team", {}).get("id", ""),
        "team_name": data.get("team", {}).get("name", ""),
        "scope": data.get("scope", ""),
        "bot_user_id": data.get("bot_user_id", "")
    }