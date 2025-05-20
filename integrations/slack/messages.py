"""Implementation of Slack message functions."""

import os
import requests
import json

def post_message(channel, text, token=None, blocks=None, thread_ts=None):
    """
    Post a message to a Slack channel.
    
    Args:
        channel: Channel ID or name to post to
        text: Message text content
        token: Slack OAuth token (can be stored in environment variable)
        blocks: Message blocks for rich formatting (optional)
        thread_ts: Thread timestamp to reply to (optional)
        
    Returns:
        Dictionary with message ID and timestamp
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
    
    payload = {
        "channel": channel,
        "text": text
    }
    
    if blocks:
        payload["blocks"] = blocks
        
    if thread_ts:
        payload["thread_ts"] = thread_ts
    
    response = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers=headers,
        data=json.dumps(payload)
    )
    
    if response.status_code != 200:
        raise ValueError(f"Error posting message: {response.text}")
    
    data = response.json()
    if not data.get("ok"):
        raise ValueError(f"Error from Slack API: {data.get('error')}")
    
    return {
        "message_id": data.get("message", {}).get("client_msg_id", ""),
        "timestamp": data.get("ts", ""),
        "channel": data.get("channel")
    }