"""Discord trigger handlers for FlowForge integration."""

import os
import asyncio
import threading
import json
import time
from typing import Dict, Any, List, Optional, Union, Callable
import discord
from discord.ext import commands

# Import to get _get_discord_client function
from integrations.discord.discord import _get_discord_client

# Global registry for active triggers
_active_triggers = {
    "message_received": {},
    "reaction_added": {},
    "webhook_received": {}
}

# Callback registry for triggers
_trigger_callbacks = {
    "message_received": {},
    "reaction_added": {},
    "webhook_received": {}
}

# Ensure client is initialized with events
_client_initialized = False

def _ensure_client_initialized():
    """Ensure the Discord client is initialized with event handlers."""
    global _client_initialized
    
    if not _client_initialized:
        client = _get_discord_client()
        
        # Set up event handlers
        @client.event
        async def on_ready():
            print(f'Discord bot logged in as {client.user.name} ({client.user.id})')
        
        @client.event
        async def on_message(message):
            # Ignore messages from the bot itself
            if message.author == client.user:
                return
            
            # Check if we're monitoring this channel
            channel_id = str(message.channel.id)
            for trigger_id, config in _active_triggers["message_received"].items():
                if channel_id in config.get("channel_ids", []):
                    # Trigger matched - call the callback
                    callback = _trigger_callbacks["message_received"].get(trigger_id)
                    if callback:
                        # Prepare data for callback
                        data = {
                            "author_id": str(message.author.id),
                            "author_name": message.author.name,
                            "content": message.content,
                            "message_id": str(message.id),
                            "channel_id": channel_id,
                            "timestamp": message.created_at.isoformat(),
                            "guild_id": str(message.guild.id) if message.guild else None
                        }
                        
                        # Call the callback
                        callback(data)
        
        @client.event
        async def on_reaction_add(reaction, user):
            # Ignore reactions from the bot itself
            if user == client.user:
                return
            
            channel_id = str(reaction.message.channel.id)
            
            for trigger_id, config in _active_triggers["reaction_added"].items():
                channel_ids = config.get("channel_ids", [])
                
                # If channel_ids is empty, monitor all channels
                if not channel_ids or channel_id in channel_ids:
                    # Trigger matched - call the callback
                    callback = _trigger_callbacks["reaction_added"].get(trigger_id)
                    if callback:
                        # Prepare data for callback
                        data = {
                            "user_id": str(user.id),
                            "user_name": user.name,
                            "message_id": str(reaction.message.id),
                            "emoji": str(reaction.emoji),
                            "channel_id": channel_id,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "guild_id": str(reaction.message.guild.id) if reaction.message.guild else None
                        }
                        
                        # Call the callback
                        callback(data)
        
        _client_initialized = True

def _register_trigger_callback(trigger_type: str, trigger_id: str, callback: Callable):
    """Register a callback for a trigger."""
    _trigger_callbacks[trigger_type][trigger_id] = callback

def message_received(channel_ids: List[str], callback: Optional[Callable] = None) -> Dict[str, Any]:
    """
    Trigger for when a new message is received in monitored channels.
    
    Args:
        channel_ids: IDs of Discord channels to monitor
        callback: Optional callback function to call when trigger fires
    
    Returns:
        Dictionary with trigger registration info
    """
    try:
        # Ensure client is initialized
        _ensure_client_initialized()
        
        # Generate a unique ID for this trigger instance
        trigger_id = f"message_received_{id(channel_ids)}_{time.time()}"
        
        # Store the trigger configuration
        _active_triggers["message_received"][trigger_id] = {
            "channel_ids": channel_ids
        }
        
        # Register callback if provided
        if callback:
            _register_trigger_callback("message_received", trigger_id, callback)
        
        return {
            "trigger_id": trigger_id,
            "type": "message_received",
            "channel_ids": channel_ids,
            "status": "active"
        }
    
    except Exception as e:
        print(f"Error setting up message_received trigger: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

def reaction_added(channel_ids: Optional[List[str]] = None, callback: Optional[Callable] = None) -> Dict[str, Any]:
    """
    Trigger for when a reaction is added to a message.
    
    Args:
        channel_ids: Optional IDs of Discord channels to monitor (if None, monitor all)
        callback: Optional callback function to call when trigger fires
    
    Returns:
        Dictionary with trigger registration info
    """
    try:
        # Ensure client is initialized
        _ensure_client_initialized()
        
        # Generate a unique ID for this trigger instance
        trigger_id = f"reaction_added_{id(channel_ids)}_{time.time()}"
        
        # Store the trigger configuration
        _active_triggers["reaction_added"][trigger_id] = {
            "channel_ids": channel_ids or []
        }
        
        # Register callback if provided
        if callback:
            _register_trigger_callback("reaction_added", trigger_id, callback)
        
        return {
            "trigger_id": trigger_id,
            "type": "reaction_added",
            "channel_ids": channel_ids or [],
            "status": "active"
        }
    
    except Exception as e:
        print(f"Error setting up reaction_added trigger: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

# Note: webhook_received would normally be implemented using a web server
# This is a simplified implementation for this example
def webhook_received(webhook_id: str, callback: Optional[Callable] = None) -> Dict[str, Any]:
    """
    Trigger for when data is received on a Discord webhook.
    This is a placeholder as it would require a web server to implement fully.
    
    Args:
        webhook_id: ID of the webhook to monitor
        callback: Optional callback function to call when trigger fires
    
    Returns:
        Dictionary with trigger registration info
    """
    return {
        "message": "Webhook triggers require a web server component. This is a placeholder.",
        "webhook_id": webhook_id,
        "status": "not_implemented"
    }

def remove_trigger(trigger_id: str) -> Dict[str, Any]:
    """
    Remove a registered trigger.
    
    Args:
        trigger_id: ID of the trigger to remove
    
    Returns:
        Dictionary with operation info
    """
    # Check all trigger types
    for trigger_type in _active_triggers:
        if trigger_id in _active_triggers[trigger_type]:
            # Remove trigger config
            del _active_triggers[trigger_type][trigger_id]
            
            # Remove callback if registered
            if trigger_id in _trigger_callbacks[trigger_type]:
                del _trigger_callbacks[trigger_type][trigger_id]
            
            return {
                "trigger_id": trigger_id,
                "type": trigger_type,
                "status": "removed"
            }
    
    return {
        "error": f"Trigger ID {trigger_id} not found",
        "success": False
    }