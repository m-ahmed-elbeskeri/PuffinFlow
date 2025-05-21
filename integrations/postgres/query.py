"""PostgreSQL query execution module for FlowForge."""

from typing import Dict, Any, List, Optional, Union
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Warning: psycopg2 not installed. Please install it with 'pip install psycopg2-binary'")
    psycopg2 = None

def query(connection, sql: str, parameters: Optional[Union[Dict[str, Any], List[Any], tuple]] = None) -> Dict[str, Any]:
    """
    Execute a SQL query and return results.
    
    Args:
        connection: Database connection object from connect or connect_with_creds
        sql: SQL query to execute
        parameters: Query parameters (for parameterized queries)
    
    Returns:
        Dictionary with rows, row count, success status, and error if any
    """
    if connection is None:
        return {
            "rows": [],
            "row_count": 0,
            "success": False,
            "error": "No connection provided"
        }
    
    try:
        # Create a cursor with dictionary results
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Execute the query
            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)
            
            # Get the results
            try:
                rows = cursor.fetchall()
                
                # Convert rows to list of dictionaries for better serialization
                result_rows = [dict(row) for row in rows]
                
                # Return results
                return {
                    "rows": result_rows,
                    "row_count": len(result_rows),
                    "success": True,
                    "error": None
                }
            except psycopg2.ProgrammingError as e:
                # No results to fetch (e.g., for CREATE, INSERT, etc.)
                return {
                    "rows": [],
                    "row_count": 0,
                    "success": True,
                    "error": None
                }
    
    except Exception as e:
        # Handle errors
        connection.rollback()
        return {
            "rows": [],
            "row_count": 0,
            "success": False,
            "error": str(e)
        }

def execute(connection, sql: str, parameters: Optional[Union[Dict[str, Any], List[Any], tuple]] = None) -> Dict[str, Any]:
    """
    Execute a non-query SQL statement (INSERT, UPDATE, DELETE).
    
    Args:
        connection: Database connection object from connect or connect_with_creds
        sql: SQL statement to execute
        parameters: Query parameters (for parameterized queries)
    
    Returns:
        Dictionary with affected rows, success status, and error if any
    """
    if connection is None:
        return {
            "affected_rows": 0,
            "success": False,
            "error": "No connection provided"
        }
    
    try:
        # Create a cursor
        with connection.cursor() as cursor:
            # Execute the statement
            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)
            
            # Get the affected row count
            affected_rows = cursor.rowcount
            
            # Commit the changes
            connection.commit()
            
            # Return results
            return {
                "affected_rows": affected_rows,
                "success": True,
                "error": None
            }
    
    except Exception as e:
        # Handle errors
        connection.rollback()
        return {
            "affected_rows": 0,
            "success": False,
            "error": str(e)
        }