"""Progress reporting module for the prompts integration."""

import time
import sys

def progress(message=None, percent=None, total=None, current=None):
    """
    Show progress to the user.
    
    Args:
        message: Optional message to display
        percent: Progress as a percentage (0-100)
        total: Total number of items (used with current)
        current: Current item number
        
    Returns:
        Dictionary with the status
    """
    if percent is None and total is not None and current is not None:
        try:
            percent = (float(current) / float(total)) * 100
        except (ValueError, ZeroDivisionError):
            percent = 0
    
    # Default to 0% if no percentage provided
    if percent is None:
        percent = 0
    
    # Cap percentage between 0 and 100
    percent = max(0, min(100, percent))
    
    # Calculate the number of bar segments to fill
    bar_length = 30
    filled_length = int(bar_length * percent / 100)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    # Format the output
    if message:
        output = f"\r{message}: [{bar}] {percent:.1f}%"
    else:
        output = f"\r[{bar}] {percent:.1f}%"
    
    # Add current/total if provided
    if total is not None and current is not None:
        output += f" ({current}/{total})"
    
    # Print without newline and flush
    sys.stdout.write(output)
    sys.stdout.flush()
    
    # Add newline if completed
    if percent >= 100:
        sys.stdout.write("\n")
        sys.stdout.flush()
    
    return {"status": "updated", "percent": percent}