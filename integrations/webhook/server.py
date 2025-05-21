"""Webhook server implementation for FlowForge."""

import os
import threading
import logging
import json
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, Tuple

# Set up logging
logger = logging.getLogger(__name__)

# Global server instance
_server_instance = None
_server_thread = None
_server_info = {
    'running': False,
    'host': '0.0.0.0',
    'port': 8000,
    'url': 'http://localhost:8000'
}

class WebhookRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for webhook requests."""
    
    def _prepare_response(self, status: int, body: str, content_type: str = 'text/plain') -> None:
        """Prepare HTTP response."""
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))
    
    def _parse_request(self) -> Tuple[str, Dict[str, str], Dict[str, Any], Any]:
        """Parse the incoming request and return path, headers, query params, and body."""
        # Parse URL and query parameters
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        # Parse query params
        query_params = {}
        if parsed_url.query:
            query_dict = parse_qs(parsed_url.query)
            for key, values in query_dict.items():
                query_params[key] = values[0] if len(values) == 1 else values
        
        # Extract headers
        headers = {}
        for header in self.headers:
            headers[header] = self.headers[header]
        
        # Extract body if available
        body = None
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            body_raw = self.rfile.read(content_length)
            
            # Try to parse as JSON if Content-Type is application/json
            content_type = self.headers.get('Content-Type', '').lower()
            if 'application/json' in content_type:
                try:
                    body = json.loads(body_raw)
                except json.JSONDecodeError:
                    body = body_raw.decode('utf-8')
            else:
                # Return as string for other content types
                body = body_raw.decode('utf-8')
        
        return path, headers, query_params, body
    
    def _handle_request(self, method: str) -> None:
        """Generic request handler for all HTTP methods."""
        try:
            # Parse the request
            path, headers, query_params, body = self._parse_request()
            
            # Import webhook module here to avoid circular imports
            from . import webhook
            
            # Process the webhook
            response = webhook.handle_webhook_request(
                path=path,
                method=method,
                headers=headers,
                query_params=query_params,
                body=body
            )
            
            # Send response
            status = response.get('status', 200)
            response_body = response.get('body', '')
            content_type = response.get('headers', {}).get('Content-Type', 'text/plain')
            
            self._prepare_response(status, response_body, content_type)
            
        except Exception as e:
            logger.error(f"Error handling {method} request: {str(e)}")
            self._prepare_response(500, f"Internal Server Error: {str(e)}")
    
    def do_GET(self):
        """Handle GET requests."""
        self._handle_request('GET')
    
    def do_POST(self):
        """Handle POST requests."""
        self._handle_request('POST')
    
    def do_PUT(self):
        """Handle PUT requests."""
        self._handle_request('PUT')
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        self._handle_request('DELETE')
    
    def do_PATCH(self):
        """Handle PATCH requests."""
        self._handle_request('PATCH')
    
    def log_message(self, format, *args):
        """Override log_message to use our logger."""
        logger.info(f"{self.client_address[0]} - {format % args}")


def _server_thread_func(server: HTTPServer) -> None:
    """Function to run the server in a separate thread."""
    global _server_info
    _server_info['running'] = True
    
    try:
        logger.info(f"Webhook server running at {_server_info['url']}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Webhook server error: {str(e)}")
    finally:
        _server_info['running'] = False
        logger.info("Webhook server stopped")


def start_server(host: str = '0.0.0.0', port: int = 8000) -> Dict[str, Any]:
    """
    Start the webhook server.
    
    Args:
        host: Host to bind to
        port: Port to listen on
        
    Returns:
        Dictionary with server status
    """
    global _server_instance, _server_thread, _server_info
    
    # Check if server is already running
    if is_server_running():
        return {
            'status': 'already_running',
            'url': _server_info['url']
        }
    
    # Try to create and start the server
    try:
        # Create server
        server = HTTPServer((host, port), WebhookRequestHandler)
        
        # Update server info
        _server_info['host'] = host
        _server_info['port'] = port
        
        # Determine server URL
        if host == '0.0.0.0':
            # Use localhost for display
            _server_info['url'] = f"http://localhost:{port}"
        else:
            _server_info['url'] = f"http://{host}:{port}"
        
        # Update environment variable for webhook URLs
        os.environ['FLOWFORGE_WEBHOOK_BASE_URL'] = _server_info['url']
        
        # Create and start server thread
        _server_instance = server
        _server_thread = threading.Thread(target=_server_thread_func, args=(server,), daemon=True)
        _server_thread.start()
        
        logger.info(f"Started webhook server at {_server_info['url']}")
        
        # Wait a bit to ensure the server starts
        time.sleep(0.5)
        
        return {
            'status': 'started',
            'url': _server_info['url']
        }
        
    except Exception as e:
        logger.error(f"Failed to start webhook server: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


def stop_server() -> Dict[str, Any]:
    """
    Stop the webhook server.
    
    Returns:
        Dictionary with server status
    """
    global _server_instance, _server_info
    
    if not is_server_running() or _server_instance is None:
        return {
            'status': 'not_running'
        }
    
    try:
        # Stop the server
        _server_instance.shutdown()
        _server_instance.server_close()
        _server_instance = None
        
        logger.info("Stopped webhook server")
        
        return {
            'status': 'stopped'
        }
        
    except Exception as e:
        logger.error(f"Error stopping webhook server: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


def is_server_running() -> bool:
    """
    Check if the webhook server is running.
    
    Returns:
        True if server is running, False otherwise
    """
    return _server_info['running']


def get_server_info() -> Dict[str, Any]:
    """
    Get information about the webhook server.
    
    Returns:
        Dictionary with server information
    """
    return {
        'running': _server_info['running'],
        'host': _server_info['host'],
        'port': _server_info['port'],
        'url': _server_info['url']
    }