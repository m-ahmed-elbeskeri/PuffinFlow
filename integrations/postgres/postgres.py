"""PostgreSQL database connection module for FlowForge."""

import os
import re
from typing import Dict, Any, Optional, Union
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Warning: psycopg2 not installed. Please install it with 'pip install psycopg2-binary'")
    psycopg2 = None

def connect(host: str, database: str, user: str, password: str, port: int = 5432) -> Dict[str, Any]:
    """
    Connect to a PostgreSQL database with explicit credentials.
    
    Args:
        host: Database server hostname or IP
        database: Database name
        user: Database username
        password: Database password
        port: Database server port (default: 5432)
    
    Returns:
        Dictionary with connection object, success status, and error if any
    """
    if psycopg2 is None:
        return {
            "connection": None,
            "success": False,
            "error": "psycopg2 library not installed. Please install with 'pip install psycopg2-binary'"
        }
    
    try:
        conn = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            port=port
        )
        return {
            "connection": conn,
            "success": True,
            "error": None
        }
    except Exception as e:
        return {
            "connection": None,
            "success": False,
            "error": str(e)
        }

def connect_with_creds(creds_source: str = "env", conn_string: Optional[str] = None) -> Dict[str, Any]:
    """
    Connect to PostgreSQL using credentials from environment variables or connection string.
    
    Args:
        creds_source: Source of credentials:
            - 'env': use environment variables POSTGRES_HOST, POSTGRES_PORT, etc.
            - 'conn_string': use the provided connection string
        conn_string: PostgreSQL connection string (required when creds_source='conn_string')
    
    Returns:
        Dictionary with connection object, success status, and error if any
    """
    if psycopg2 is None:
        return {
            "connection": None,
            "success": False,
            "error": "psycopg2 library not installed. Please install with 'pip install psycopg2-binary'"
        }
    
    try:
        if creds_source == "env":
            # Get credentials from environment variables
            host = os.environ.get("POSTGRES_HOST")
            port = int(os.environ.get("POSTGRES_PORT", "5432"))
            database = os.environ.get("POSTGRES_DATABASE") or os.environ.get("POSTGRES_DB")
            user = os.environ.get("POSTGRES_USER")
            password = os.environ.get("POSTGRES_PASSWORD")
            
            # Check if required variables are present
            missing_vars = []
            if not host: missing_vars.append("POSTGRES_HOST")
            if not database: missing_vars.append("POSTGRES_DATABASE or POSTGRES_DB")
            if not user: missing_vars.append("POSTGRES_USER")
            if not password: missing_vars.append("POSTGRES_PASSWORD")
            
            if missing_vars:
                return {
                    "connection": None,
                    "success": False,
                    "error": f"Missing environment variables: {', '.join(missing_vars)}"
                }
            
            # Connect with environment variables
            conn = psycopg2.connect(
                host=host,
                database=database,
                user=user,
                password=password,
                port=port
            )
        
        elif creds_source == "conn_string":
            # Check if connection string is provided
            if not conn_string:
                return {
                    "connection": None,
                    "success": False,
                    "error": "Connection string is required when creds_source='conn_string'"
                }
            
            # Connect with connection string
            conn = psycopg2.connect(conn_string)
        
        else:
            return {
                "connection": None,
                "success": False,
                "error": f"Invalid creds_source: {creds_source}. Must be 'env' or 'conn_string'"
            }
        
        # Return successful connection
        return {
            "connection": conn,
            "success": True,
            "error": None
        }
    
    except Exception as e:
        return {
            "connection": None,
            "success": False,
            "error": str(e)
        }

def disconnect(connection) -> Dict[str, Any]:
    """
    Close a database connection.
    
    Args:
        connection: Database connection object to close
    
    Returns:
        Dictionary with success status
    """
    if connection is None:
        return {"success": False, "error": "No connection provided"}
    
    try:
        connection.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}