"""Webhook triggers for flow execution."""

import time
import threading
from typing import Dict, Any, Optional

def webhook_trigger(
    path: str,
    method: str = "POST",
    auth_token: Optional[str] = None,
    timeout: int = 0,
    auto_start_server: bool = True,
    server_port: int = 8000
) -> Dict[str, Any]:
    """
    Flow trigger that waits for an HTTP webhook request.
    
    Args:
        path: The URL path for the webhook
        method: HTTP method to listen for
        auth_token: Optional authentication token
        timeout: Maximum time to wait (0 = wait forever)
        auto_start_server: Whether to start the server if not running
        server_port: Port for the webhook server
        
    Returns:
        Dictionary with webhook request details
    """
    from . import webhook
    from . import server
    
    # Auto-start server if needed
    if auto_start_server:
        is_running = server.is_server_running()
        if not is_running:
            server.start_server(port=server_port)
    
    # Create webhook and wait for trigger
    webhook_config = webhook.create_webhook(
        path=path,
        method=method,
        auth_token=auth_token,
        description="Flow trigger webhook"
    )
    
    webhook_id = webhook_config["webhook_id"]
    
    # Set up event for notification
    trigger_event = threading.Event()
    trigger_data = {}
    
    def callback(data):
        nonlocal trigger_data
        trigger_data = data
        trigger_event.set()
    
    # Register callback
    webhook.register_flow_callback(webhook_id, callback)
    
    # Wait for trigger or timeout
    if timeout > 0:
        triggered = trigger_event.wait(timeout)
    else:
        triggered = trigger_event.wait()
    
    # Clean up webhook
    webhook.delete_webhook(webhook_id)
    
    if not triggered:
        return {
            "triggered": False,
            "message": "Webhook trigger timed out"
        }
    
    # Return webhook data
    return {
        "triggered": True,
        "method": trigger_data.get("method"),
        "path": trigger_data.get("path"),
        "headers": trigger_data.get("headers", {}),
        "query_params": trigger_data.get("query_params", {}),
        "body": trigger_data.get("body"),
        "timestamp": trigger_data.get("timestamp", time.time())
    }