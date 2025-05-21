"""Gmail trigger implementation for event-based flows."""

import os
import json
import time
import threading
import requests
from pathlib import Path
import uuid
from datetime import datetime, timedelta

# Import gmail module functions
from .gmail import get_emails, mark_as_read, _get_gmail_service

# Configuration paths
CONFIG_DIR = Path.home() / ".flowforge" / "gmail"
TRIGGERS_FILE = CONFIG_DIR / "triggers.json"

# Ensure config directory exists
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Dictionary to track active triggers
active_triggers = {}

def _load_triggers():
    """Load triggers from file."""
    if TRIGGERS_FILE.exists():
        try:
            with open(TRIGGERS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_triggers(triggers):
    """Save triggers to file."""
    with open(TRIGGERS_FILE, 'w') as f:
        json.dump(triggers, f, indent=2)

def _check_new_emails(trigger_config):
    """
    Check for new emails based on trigger configuration.
    
    Args:
        trigger_config: Trigger configuration
    """
    try:
        trigger_id = trigger_config['id']
        query = trigger_config['query']
        webhook_url = trigger_config.get('webhook_url')
        max_results = trigger_config.get('max_results', 10)
        
        # Track history for this trigger
        if 'history' not in trigger_config:
            trigger_config['history'] = []
        
        # Get history of processed message IDs
        processed_ids = set(trigger_config['history'])
        
        # Get new emails
        result = get_emails(query=query, max_results=max_results)
        emails = result.get('emails', [])
        new_emails = []
        
        # Filter out already processed emails
        for email in emails:
            if email['id'] not in processed_ids:
                new_emails.append(email)
                processed_ids.add(email['id'])
        
        # Update history (keep last 1000 IDs)
        trigger_config['history'] = list(processed_ids)[-1000:]
        
        # Save updated trigger data
        triggers = _load_triggers()
        if trigger_id in triggers:
            triggers[trigger_id]['history'] = trigger_config['history']
            _save_triggers(triggers)
        
        # Process new emails if found
        if new_emails and webhook_url:
            # Send webhook notification
            try:
                requests.post(
                    webhook_url,
                    json={
                        'trigger_id': trigger_id,
                        'emails': new_emails,
                        'count': len(new_emails),
                        'timestamp': datetime.now().isoformat()
                    },
                    timeout=10
                )
            except Exception as e:
                print(f"Error calling webhook {webhook_url}: {str(e)}")
        
        return len(new_emails)
        
    except Exception as e:
        print(f"Error checking emails for trigger {trigger_config.get('id')}: {str(e)}")
        return 0

def _trigger_worker(trigger_id):
    """
    Worker thread for a Gmail trigger.
    
    Args:
        trigger_id: ID of the trigger to monitor
    """
    while trigger_id in active_triggers:
        triggers = _load_triggers()
        trigger_config = triggers.get(trigger_id)
        
        if not trigger_config:
            # Trigger no longer exists
            if trigger_id in active_triggers:
                del active_triggers[trigger_id]
            break
        
        # Check for new emails
        count = _check_new_emails(trigger_config)
        
        # Log activity if configured
        if trigger_config.get('log_activity', False):
            print(f"Trigger {trigger_id} checked: {count} new emails found")
        
        # Sleep for the configured interval
        check_interval = trigger_config.get('check_interval', 60)
        time.sleep(check_interval)

def create_trigger(query="is:unread", check_interval=60, webhook_url=None, max_results=10):
    """
    Create a Gmail trigger for incoming emails.
    
    Args:
        query: Gmail search query for emails to trigger on
        check_interval: Interval in seconds to check for new emails
        webhook_url: Webhook URL to call when new emails are detected
        max_results: Maximum number of emails to process per check
        
    Returns:
        Dictionary with trigger_id and status
    """
    try:
        # Validate Gmail credentials
        _get_gmail_service()
        
        # Generate trigger ID
        trigger_id = str(uuid.uuid4())
        
        # Create trigger configuration
        trigger_config = {
            'id': trigger_id,
            'query': query,
            'check_interval': check_interval,
            'webhook_url': webhook_url,
            'max_results': max_results,
            'created_at': datetime.now().isoformat(),
            'status': 'active',
            'history': []
        }
        
        # Save trigger configuration
        triggers = _load_triggers()
        triggers[trigger_id] = trigger_config
        _save_triggers(triggers)
        
        # Start trigger worker thread
        active_triggers[trigger_id] = True
        thread = threading.Thread(
            target=_trigger_worker,
            args=(trigger_id,),
            daemon=True
        )
        thread.start()
        
        return {
            'trigger_id': trigger_id,
            'status': 'Trigger created and activated'
        }
        
    except Exception as e:
        return {
            'trigger_id': '',
            'status': f'Error creating trigger: {str(e)}'
        }

def delete_trigger(trigger_id):
    """
    Delete a Gmail trigger.
    
    Args:
        trigger_id: ID of the trigger to delete
        
    Returns:
        Dictionary with success status
    """
    try:
        # Load triggers
        triggers = _load_triggers()
        
        # Check if trigger exists
        if trigger_id not in triggers:
            return {
                'success': False,
                'message': f'Trigger {trigger_id} not found'
            }
        
        # Stop the trigger worker
        if trigger_id in active_triggers:
            del active_triggers[trigger_id]
        
        # Remove trigger from configuration
        del triggers[trigger_id]
        _save_triggers(triggers)
        
        return {
            'success': True,
            'message': f'Trigger {trigger_id} deleted'
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Error deleting trigger: {str(e)}'
        }

def list_triggers():
    """
    List all Gmail triggers.
    
    Returns:
        Dictionary with triggers and count
    """
    try:
        triggers = _load_triggers()
        
        # Remove history from response to reduce size
        triggers_without_history = {}
        for tid, trigger in triggers.items():
            trigger_copy = trigger.copy()
            if 'history' in trigger_copy:
                trigger_copy['history_count'] = len(trigger_copy['history'])
                del trigger_copy['history']
            triggers_without_history[tid] = trigger_copy
        
        return {
            'triggers': triggers_without_history,
            'count': len(triggers)
        }
        
    except Exception as e:
        return {
            'triggers': {},
            'count': 0,
            'error': str(e)
        }

# Initialize triggers on module load
def _initialize_triggers():
    """Initialize all saved triggers on module load."""
    try:
        triggers = _load_triggers()
        
        for trigger_id, trigger_config in triggers.items():
            if trigger_config.get('status') == 'active':
                # Start trigger worker thread
                active_triggers[trigger_id] = True
                thread = threading.Thread(
                    target=_trigger_worker,
                    args=(trigger_id,),
                    daemon=True
                )
                thread.start()
                
    except Exception as e:
        print(f"Error initializing triggers: {str(e)}")

# Initialize triggers
_initialize_triggers()