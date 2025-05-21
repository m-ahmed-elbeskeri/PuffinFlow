"""Webhook integration for receiving HTTP requests to trigger flows."""

import os
import json
import uuid
import logging
import threading
import time
from typing import Dict, Any, List, Optional, Callable

# Set up logging
logger = logging.getLogger(__name__)

# Store webhook definitions
_webhooks = {}
_webhook_triggers = {}
_webhook_server_instance = None
_active_flows = {}

def create_webhook(
    path: str,
    method: str = "POST",
    auth_token: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    """
    Create a webhook endpoint to trigger flows.
    
    Args:
        path: URL path for the webhook endpoint (e.g., '/my-webhook')
        method: HTTP method to accept (default: POST)
        auth_token: Optional authentication token for webhook security
        description: Description of the webhook's purpose
        
    Returns:
        Dictionary with webhook details
    """
    # Normalize path to ensure it starts with a slash
    if not path.startswith('/'):
        path = '/' + path
    
    # Generate a unique ID for this webhook
    webhook_id = str(uuid.uuid4())
    
    # Store the webhook configuration
    webhook_config = {
        'id': webhook_id,
        'path': path,
        'method': method.upper(),
        'auth_token': auth_token,
        'description': description,
        'created_at': time.time(),
        'flow_id': os.environ.get('FLOWFORGE_CURRENT_FLOW_ID', 'unknown')
    }
    
    _webhooks[webhook_id] = webhook_config
    
    # Register the webhook with path as key for lookup
    path_key = f"{method.upper()}:{path}"
    _webhook_triggers[path_key] = webhook_id
    
    logger.info(f"Created webhook: {webhook_id} for path {path} with method {method}")
    
    # Derive the full URL (this will be updated when the server starts)
    base_url = os.environ.get('FLOWFORGE_WEBHOOK_BASE_URL', 'http://localhost:8000')
    webhook_url = f"{base_url}{path}"
    
    # Return the webhook details
    return {
        'webhook_id': webhook_id,
        'url': webhook_url,
        'method': method.upper(),
        'path': path,
        'auth_required': auth_token is not None
    }

def register_flow_callback(webhook_id: str, callback: Callable) -> None:
    """
    Register a flow callback function to be executed when a webhook is triggered.
    
    Args:
        webhook_id: ID of the webhook
        callback: Function to call when webhook is triggered
    """
    _active_flows[webhook_id] = callback
    logger.info(f"Registered flow callback for webhook: {webhook_id}")

def handle_webhook_request(path: str, method: str, headers: Dict[str, str], 
                          query_params: Dict[str, Any], body: Any) -> Dict[str, Any]:
    """
    Process an incoming webhook request and trigger the associated flow.
    
    Args:
        path: Request path
        method: HTTP method
        headers: Request headers
        query_params: Query parameters
        body: Request body
        
    Returns:
        Response to send back to the client
    """
    path_key = f"{method.upper()}:{path}"
    
    # Check if this path is registered
    if path_key not in _webhook_triggers:
        logger.warning(f"Received request for unregistered webhook: {path_key}")
        return {
            'status': 404,
            'body': 'Webhook not found',
            'headers': {'Content-Type': 'text/plain'}
        }
    
    webhook_id = _webhook_triggers[path_key]
    webhook_config = _webhooks.get(webhook_id)
    
    if not webhook_config:
        logger.error(f"Webhook configuration missing for ID: {webhook_id}")
        return {
            'status': 500,
            'body': 'Webhook configuration error',
            'headers': {'Content-Type': 'text/plain'}
        }
    
    # Check authentication token if required
    if webhook_config.get('auth_token'):
        auth_header = headers.get('Authorization', '')
        token = None
        
        # Extract token from header
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        elif auth_header.startswith('Token '):
            token = auth_header[6:]
            
        # Check token in query params if not in header
        if not token and 'token' in query_params:
            token = query_params['token']
            
        if token != webhook_config['auth_token']:
            logger.warning(f"Authentication failed for webhook: {webhook_id}")
            return {
                'status': 401,
                'body': 'Unauthorized',
                'headers': {'Content-Type': 'text/plain'}
            }
    
    # Trigger the associated flow if registered
    if webhook_id in _active_flows:
        try:
            callback = _active_flows[webhook_id]
            
            # Prepare webhook payload with all request details
            webhook_payload = {
                'webhook_id': webhook_id,
                'method': method,
                'path': path,
                'headers': headers,
                'query_params': query_params,
                'body': body,
                'timestamp': time.time()
            }
            
            # Run the flow callback in a separate thread to avoid blocking
            thread = threading.Thread(
                target=lambda: callback(webhook_payload),
                daemon=True
            )
            thread.start()
            
            logger.info(f"Triggered flow for webhook: {webhook_id}")
            
            return {
                'status': 200,
                'body': json.dumps({'status': 'success', 'message': 'Webhook received and processing started'}),
                'headers': {'Content-Type': 'application/json'}
            }
            
        except Exception as e:
            logger.error(f"Error triggering flow for webhook {webhook_id}: {str(e)}")
            return {
                'status': 500,
                'body': json.dumps({'status': 'error', 'message': 'Internal server error processing webhook'}),
                'headers': {'Content-Type': 'application/json'}
            }
    else:
        # Record the webhook hit but no active flow to process it
        logger.warning(f"Received request for webhook {webhook_id} but no flow is registered to handle it")
        return {
            'status': 202,  # Accepted but not processed
            'body': json.dumps({'status': 'received', 'message': 'Webhook received but no active handler'}),
            'headers': {'Content-Type': 'application/json'}
        }

def list_webhooks() -> List[Dict[str, Any]]:
    """
    List all registered webhooks.
    
    Returns:
        List of webhook configurations
    """
    return list(_webhooks.values())

def get_webhook(webhook_id: str) -> Optional[Dict[str, Any]]:
    """
    Get details of a specific webhook.
    
    Args:
        webhook_id: ID of the webhook
        
    Returns:
        Webhook configuration or None if not found
    """
    return _webhooks.get(webhook_id)

def delete_webhook(webhook_id: str) -> bool:
    """
    Delete a webhook.
    
    Args:
        webhook_id: ID of the webhook
        
    Returns:
        True if webhook was deleted, False otherwise
    """
    if webhook_id not in _webhooks:
        return False
    
    webhook_config = _webhooks[webhook_id]
    path_key = f"{webhook_config['method']}:{webhook_config['path']}"
    
    # Remove from both dictionaries
    del _webhooks[webhook_id]
    if path_key in _webhook_triggers:
        del _webhook_triggers[path_key]
    
    # Remove any active flow callback
    if webhook_id in _active_flows:
        del _active_flows[webhook_id]
    
    logger.info(f"Deleted webhook: {webhook_id}")
    return True