"""Implementation of Slack user functions."""

import os
import requests
import json

def list_users(token=None):
    """
    List users in the Slack workspace.
    
    Args:
        token: Slack OAuth token (can be stored in environment variable)
        
    Returns:
        Dictionary with list of users
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
    
    response = requests.get(
        "https://slack.com/api/users.list",
        headers=headers
    )
    
    if response.status_code != 200:
        raise ValueError(f"Error listing users: {response.text}")
    
    data = response.json()
    if not data.get("ok"):
        raise ValueError(f"Error from Slack API: {data.get('error')}")
    
    return {
        "users": data.get("members", [])
    }