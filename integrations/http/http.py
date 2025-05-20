"""HTTP integration for making requests to external services."""

import requests
import json
import urllib.parse
import logging
from typing import Dict, Any, Optional, Union

# Set up logging
logger = logging.getLogger(__name__)

def request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Any = None,
    json: Optional[Dict[str, Any]] = None,
    auth: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    verify: bool = True
) -> Dict[str, Any]:
    """
    Make a generic HTTP request with customizable parameters.
    
    Args:
        url: The URL to send the request to
        method: HTTP method to use (GET, POST, PUT, DELETE, PATCH)
        headers: Dictionary of HTTP headers
        params: Dictionary of URL parameters
        data: Request body data
        json: JSON request body (alternative to data)
        auth: Dictionary with 'username' and 'password' keys for basic auth
        timeout: Request timeout in seconds
        verify: Whether to verify SSL certificates
        
    Returns:
        Dictionary with response details
    """
    logger.info(f"Making {method} request to {url}")
    
    # Validate and normalize inputs
    if headers is None:
        headers = {}
    if params is None:
        params = {}
    
    # Process auth if provided
    auth_tuple = None
    if auth and isinstance(auth, dict):
        if 'username' in auth and 'password' in auth:
            auth_tuple = (auth['username'], auth['password'])
    
    try:
        # Make the request
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            data=data,
            json=json,
            auth=auth_tuple,
            timeout=timeout,
            verify=verify
        )
        
        # Try to parse response as JSON
        json_response = None
        try:
            json_response = response.json()
        except (ValueError, json.JSONDecodeError):
            # Response is not JSON
            pass
        
        # Prepare result
        result = {
            "status": response.status_code,
            "response": response.text,
            "headers": dict(response.headers),
            "url": response.url,
            "success": 200 <= response.status_code < 300
        }
        
        if json_response is not None:
            result["json"] = json_response
        
        return result
        
    except requests.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        return {
            "status": 0,
            "response": str(e),
            "headers": {},
            "url": url,
            "error": str(e),
            "success": False
        }

def get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Make a HTTP GET request.
    
    Args:
        url: The URL to send the request to
        headers: Dictionary of HTTP headers
        params: Dictionary of URL parameters
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with response details
    """
    return request(
        url=url,
        method="GET",
        headers=headers,
        params=params,
        timeout=timeout
    )

def post(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Any = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Make a HTTP POST request.
    
    Args:
        url: The URL to send the request to
        headers: Dictionary of HTTP headers
        params: Dictionary of URL parameters
        data: Request body data
        json: JSON request body (alternative to data)
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with response details
    """
    return request(
        url=url,
        method="POST",
        headers=headers,
        params=params,
        data=data,
        json=json,
        timeout=timeout
    )

def put(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Any = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Make a HTTP PUT request.
    
    Args:
        url: The URL to send the request to
        headers: Dictionary of HTTP headers
        params: Dictionary of URL parameters
        data: Request body data
        json: JSON request body (alternative to data)
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with response details
    """
    return request(
        url=url,
        method="PUT",
        headers=headers,
        params=params,
        data=data,
        json=json,
        timeout=timeout
    )

def delete(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Any = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Make a HTTP DELETE request.
    
    Args:
        url: The URL to send the request to
        headers: Dictionary of HTTP headers
        params: Dictionary of URL parameters
        data: Request body data
        json: JSON request body (alternative to data)
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with response details
    """
    return request(
        url=url,
        method="DELETE",
        headers=headers,
        params=params,
        data=data,
        json=json,
        timeout=timeout
    )

def patch(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Any = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Make a HTTP PATCH request.
    
    Args:
        url: The URL to send the request to
        headers: Dictionary of HTTP headers
        params: Dictionary of URL parameters
        data: Request body data
        json: JSON request body (alternative to data)
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with response details
    """
    return request(
        url=url,
        method="PATCH",
        headers=headers,
        params=params,
        data=data,
        json=json,
        timeout=timeout
    )