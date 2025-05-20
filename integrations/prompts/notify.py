
"""User notification module for the prompts integration."""

import re

def notify(message, level="info"):
    """
    Display a notification message to the user.
    
    Args:
        message: The message to display (can include template variables using {step_id.output_name})
        level: Notification level (info, success, warning, error)
        
    Returns:
        Dictionary with the status
    """
    # Process the message to handle templates correctly
    # Convert double curly braces to single (if present)
    if '{{' in message:
        message = message.replace('{{', '{').replace('}}', '}')
    
    # The actual template replacement happens in the FlowForge runtime engine
    # This is just to make sure the formatting is consistent
    
    prefix = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌"
    }.get(level, "ℹ️")
    
    print(f"\n{prefix} {message}")
    
    return {"status": "displayed", "level": level}