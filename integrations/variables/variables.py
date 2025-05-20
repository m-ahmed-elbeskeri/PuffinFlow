"""Variable operations for FlowForge with environment and local variable support."""

import os

def get_local(name, default=None):
    """
    Get a local flow variable.
    
    Args:
        name: Variable name
        default: Default value if variable doesn't exist
        
    Returns:
        The variable value
    """
    # This is a placeholder implementation
    # The actual implementation is in FlowEngine._execute_step_action
    # which overrides this function with direct access to flow_variables
    return {"value": default}

def set_local(name, value):
    """
    Set a local flow variable.
    
    Args:
        name: Variable name
        value: Value to set
        
    Returns:
        The variable value that was set
    """
    # This is a placeholder implementation
    # The actual implementation is in FlowEngine._execute_step_action
    # which overrides this function with direct access to flow_variables
    return {"value": value}

def get_env(name, default=""):
    """
    Get an environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if environment variable doesn't exist
        
    Returns:
        The environment variable value
    """
    # This function can work directly with os.environ, but
    # FlowEngine._execute_step_action will override it to use its environment copy
    return {"value": os.environ.get(name, default)}

# Legacy support functions

def get(name, default=None):
    """
    Get a variable (checks local variables first, then environment).
    
    Args:
        name: Variable name
        default: Default value if variable doesn't exist
        
    Returns:
        The variable value
    """
    # This is a placeholder implementation
    # The actual implementation is in FlowEngine._execute_step_action
    return {"value": default}

def set(name, value):
    """
    Set a local flow variable (legacy method).
    
    Args:
        name: Variable name
        value: Value to set
        
    Returns:
        The variable value that was set
    """
    # This is a placeholder implementation
    # The actual implementation is in FlowEngine._execute_step_action
    return {"value": value}