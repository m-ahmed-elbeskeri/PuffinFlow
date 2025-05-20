"""Implementation of Slack channel functions."""

import os
import requests
import json

def list_channels(token=None, types="public_channel"):
    """
    List available Slack channels.
    
    Args:
        token: Slack OAuth token (can be stored in environment variable)
        types: Types of channels to include (comma-separated)
        
    Returns:
        Dictionary with list of channels
    """
    # Use environment variable if token not provided
    if token is None:
        token = os.environ.get("SLACK_TOKEN")
        if not token:
            raise ValueError("Slack token not provided and SLACK_TOKEN environment variable not set")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    params = {"types": types}
    
    response = requests.get(
        "https://slack.com/api/conversations.list",
        headers=headers,
        params=params
    )
    
    if response.status_code != 200:
        raise ValueError(f"Error listing channels: {response.text}")
    
    data = response.json()
    if not data.get("ok"):
        raise ValueError(f"Error from Slack API: {data.get('error')}")
    
    return {
        "channels": data.get("channels", [])
    }