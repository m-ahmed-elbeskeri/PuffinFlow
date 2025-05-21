"""Discord integration for FlowForge with improved message formatting."""

import os
import json
import aiohttp
import asyncio
import discord
from discord.ext import commands
from typing import Dict, Any, List, Optional, Union
import datetime

# Global discord client
_discord_client = None

def _get_discord_client():
    """Get or create Discord client."""
    global _discord_client
    
    if not _discord_client:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN environment variable is required. Please set it with your Discord bot token.")
        
        intents = discord.Intents.default()
        intents.message_content = True
        _discord_client = commands.Bot(command_prefix='!', intents=intents)
        
        # Run the client in background
        async def start_client():
            await _discord_client.start(token)
        
        # Create event loop and run client
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(start_client())
        
        # Run the loop in a separate thread
        import threading
        def run_bot():
            loop.run_forever()
        
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
    
    return _discord_client

async def _get_channel(channel_id: str):
    """Get a Discord channel by ID."""
    client = _get_discord_client()
    
    # Wait for client to be ready
    await client.wait_until_ready()
    
    # Convert channel_id to int if needed
    try:
        channel_id = int(channel_id)
    except ValueError:
        raise ValueError(f"Invalid channel ID: {channel_id}")
    
    channel = client.get_channel(channel_id)
    if not channel:
        try:
            channel = await client.fetch_channel(channel_id)
        except discord.NotFound:
            raise ValueError(f"Channel with ID {channel_id} not found")
    
    return channel

def send_message(channel_id: str, content: str, tts: bool = False) -> Dict[str, Any]:
    """
    Send a message to a Discord channel.
    
    Args:
        channel_id: ID of the Discord channel
        content: Content of the message
        tts: Whether to send as a TTS message
    
    Returns:
        Dictionary with information about the sent message
    """
    try:
        # Get event loop or create new one
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def send_async():
            channel = await _get_channel(channel_id)
            msg = await channel.send(content=content, tts=tts)
            return {
                "message_id": str(msg.id),
                "channel_id": str(msg.channel.id),
                "timestamp": msg.created_at.isoformat()
            }
        
        result = loop.run_until_complete(send_async())
        return result
    
    except Exception as e:
        print(f"Error sending Discord message: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

def send_embed(
    channel_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None,
    fields: Optional[List[Dict[str, Any]]] = None,
    image_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    author_name: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send a rich embed message to a Discord channel.
    
    Args:
        channel_id: ID of the Discord channel
        title: Title of the embed
        description: Description text of the embed
        color: Color of the embed (hex code)
        fields: List of fields to add to the embed
        image_url: URL to an image to display in the embed
        thumbnail_url: URL to a thumbnail image for the embed
        author_name: Name of the author to display in the embed
        author_icon_url: URL to an icon for the author
        footer_text: Footer text for the embed
        footer_icon_url: URL to an icon for the footer
    
    Returns:
        Dictionary with information about the sent message
    """
    try:
        # Convert color from hex to int if provided
        embed_color = None
        if color:
            if color.startswith('#'):
                color = color[1:]
            try:
                embed_color = int(color, 16)
            except ValueError:
                embed_color = 0x5865F2  # Discord blue as fallback
        
        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def send_async():
            channel = await _get_channel(channel_id)
            
            # Create embed
            embed = discord.Embed(
                title=title,
                description=description,
                color=embed_color
            )
            
            # Add fields if provided
            if fields:
                for field in fields:
                    name = field.get('name', '')
                    value = field.get('value', '')
                    inline = field.get('inline', False)
                    embed.add_field(name=name, value=value, inline=inline)
            
            # Add image if provided
            if image_url:
                embed.set_image(url=image_url)
            
            # Add thumbnail if provided
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            # Add author if provided
            if author_name:
                embed.set_author(name=author_name, icon_url=author_icon_url)
            
            # Add footer if provided
            if footer_text:
                embed.set_footer(text=footer_text, icon_url=footer_icon_url)
            
            # Set timestamp
            embed.timestamp = datetime.datetime.now()
            
            # Send the embed
            msg = await channel.send(embed=embed)
            
            return {
                "message_id": str(msg.id),
                "channel_id": str(msg.channel.id),
                "timestamp": msg.created_at.isoformat()
            }
        
        result = loop.run_until_complete(send_async())
        return result
    
    except Exception as e:
        print(f"Error sending Discord embed: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

def get_channel_info(channel_id: str) -> Dict[str, Any]:
    """
    Get information about a Discord channel.
    
    Args:
        channel_id: ID of the Discord channel
    
    Returns:
        Dictionary with information about the channel
    """
    try:
        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def get_async():
            channel = await _get_channel(channel_id)
            
            result = {
                "name": channel.name,
                "id": str(channel.id),
                "type": str(channel.type),
                "position": channel.position
            }
            
            # Add guild_id if channel is in a guild
            if hasattr(channel, "guild") and channel.guild:
                result["guild_id"] = str(channel.guild.id)
            
            # Add topic if text channel
            if hasattr(channel, "topic"):
                result["topic"] = channel.topic
            
            return result
        
        result = loop.run_until_complete(get_async())
        return result
    
    except Exception as e:
        print(f"Error getting Discord channel info: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

def get_guild_info(guild_id: str) -> Dict[str, Any]:
    """
    Get information about a Discord server (guild).
    
    Args:
        guild_id: ID of the Discord guild
    
    Returns:
        Dictionary with information about the guild
    """
    try:
        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def get_async():
            client = _get_discord_client()
            
            # Wait for client to be ready
            await client.wait_until_ready()
            
            # Convert guild_id to int if needed
            try:
                guild_id_int = int(guild_id)
            except ValueError:
                raise ValueError(f"Invalid guild ID: {guild_id}")
            
            guild = client.get_guild(guild_id_int)
            if not guild:
                try:
                    guild = await client.fetch_guild(guild_id_int)
                except discord.NotFound:
                    raise ValueError(f"Guild with ID {guild_id} not found")
            
            # Build result
            result = {
                "name": guild.name,
                "id": str(guild.id),
                "member_count": guild.member_count,
                "region": str(guild.region) if hasattr(guild, "region") else "unknown",
                "icon_url": str(guild.icon.url) if guild.icon else None,
                "owner_id": str(guild.owner_id) if hasattr(guild, "owner_id") else None,
                "created_at": guild.created_at.isoformat() if hasattr(guild, "created_at") else None
            }
            
            return result
        
        result = loop.run_until_complete(get_async())
        return result
    
    except Exception as e:
        print(f"Error getting Discord guild info: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }