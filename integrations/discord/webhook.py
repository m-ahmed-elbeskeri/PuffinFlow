"""Discord webhook functions for sending messages and managing webhooks."""

import os
import json
import aiohttp
import asyncio
from typing import Dict, Any, List, Optional, Union
import discord
from discord.ext import commands

# Import to get _get_discord_client function
from integrations.discord.discord import _get_discord_client, _get_channel

async def _create_webhook_async(channel_id: str, name: str, avatar_url: Optional[str] = None):
    """Create a webhook for a channel asynchronously."""
    channel = await _get_channel(channel_id)
    
    # Check if channel supports webhooks
    if not isinstance(channel, discord.TextChannel):
        raise ValueError(f"Channel with ID {channel_id} does not support webhooks")
    
    # Create webhook
    webhook = await channel.create_webhook(name=name, avatar=avatar_url)
    
    # Return webhook details
    return {
        "webhook_id": str(webhook.id),
        "webhook_url": webhook.url,
        "token": webhook.token,
        "channel_id": str(webhook.channel_id),
        "guild_id": str(webhook.guild_id) if webhook.guild_id else None
    }

def create_webhook(channel_id: str, name: str, avatar_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a new webhook for a Discord channel.
    
    Args:
        channel_id: ID of the Discord channel
        name: Name of the webhook
        avatar_url: URL to an avatar image for the webhook
    
    Returns:
        Dictionary with information about the created webhook
    """
    try:
        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Create webhook
        result = loop.run_until_complete(_create_webhook_async(channel_id, name, avatar_url))
        return result
    
    except Exception as e:
        print(f"Error creating Discord webhook: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

async def _send_webhook_async(
    webhook_url: str, 
    content: Optional[str] = None, 
    username: Optional[str] = None,
    avatar_url: Optional[str] = None,
    embeds: Optional[List[Dict[str, Any]]] = None
):
    """Send a message to a webhook asynchronously."""
    async with aiohttp.ClientSession() as session:
        webhook_data = {}
        
        # Add content if provided
        if content:
            webhook_data["content"] = content
        
        # Add username if provided
        if username:
            webhook_data["username"] = username
        
        # Add avatar_url if provided
        if avatar_url:
            webhook_data["avatar_url"] = avatar_url
        
        # Add embeds if provided
        if embeds:
            webhook_data["embeds"] = embeds
        
        # Send webhook
        async with session.post(webhook_url, json=webhook_data) as response:
            success = response.status >= 200 and response.status < 300
            return {
                "success": success,
                "status_code": response.status,
                "response": await response.text() if not success else None
            }

def send_webhook(
    webhook_url: str, 
    content: Optional[str] = None, 
    username: Optional[str] = None,
    avatar_url: Optional[str] = None,
    embeds: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Send a message via a Discord webhook.
    
    Args:
        webhook_url: URL of the Discord webhook
        content: Content of the message
        username: Override the webhook's username
        avatar_url: Override the webhook's avatar
        embeds: List of embeds to send
    
    Returns:
        Dictionary with information about the operation
    """
    try:
        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Send webhook
        result = loop.run_until_complete(_send_webhook_async(
            webhook_url, content, username, avatar_url, embeds
        ))
        return result
    
    except Exception as e:
        print(f"Error sending Discord webhook: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

async def _get_webhook_async(webhook_id: str):
    """Get a webhook by ID asynchronously."""
    client = _get_discord_client()
    
    # Wait for client to be ready
    await client.wait_until_ready()
    
    # Convert webhook_id to int if needed
    try:
        webhook_id_int = int(webhook_id)
    except ValueError:
        raise ValueError(f"Invalid webhook ID: {webhook_id}")
    
    # Get webhook
    webhook = None
    try:
        webhook = await client.fetch_webhook(webhook_id_int)
    except discord.NotFound:
        raise ValueError(f"Webhook with ID {webhook_id} not found")
    
    # Return webhook details
    return {
        "webhook_id": str(webhook.id),
        "webhook_url": webhook.url,
        "channel_id": str(webhook.channel_id),
        "guild_id": str(webhook.guild_id) if webhook.guild_id else None,
        "name": webhook.name,
        "avatar_url": str(webhook.avatar_url) if webhook.avatar_url else None
    }

def get_webhook(webhook_id: str) -> Dict[str, Any]:
    """
    Get information about a Discord webhook.
    
    Args:
        webhook_id: ID of the Discord webhook
    
    Returns:
        Dictionary with information about the webhook
    """
    try:
        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Get webhook
        result = loop.run_until_complete(_get_webhook_async(webhook_id))
        return result
    
    except Exception as e:
        print(f"Error getting Discord webhook: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

async def _delete_webhook_async(webhook_id: str):
    """Delete a webhook by ID asynchronously."""
    client = _get_discord_client()
    
    # Wait for client to be ready
    await client.wait_until_ready()
    
    # Convert webhook_id to int if needed
    try:
        webhook_id_int = int(webhook_id)
    except ValueError:
        raise ValueError(f"Invalid webhook ID: {webhook_id}")
    
    # Get webhook
    webhook = None
    try:
        webhook = await client.fetch_webhook(webhook_id_int)
    except discord.NotFound:
        raise ValueError(f"Webhook with ID {webhook_id} not found")
    
    # Delete webhook
    await webhook.delete()
    
    return {
        "success": True,
        "webhook_id": webhook_id
    }

def delete_webhook(webhook_id: str) -> Dict[str, Any]:
    """
    Delete a Discord webhook.
    
    Args:
        webhook_id: ID of the Discord webhook
    
    Returns:
        Dictionary with information about the operation
    """
    try:
        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Delete webhook
        result = loop.run_until_complete(_delete_webhook_async(webhook_id))
        return result
    
    except Exception as e:
        print(f"Error deleting Discord webhook: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }