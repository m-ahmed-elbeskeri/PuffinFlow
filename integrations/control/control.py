
"""Core control-flow primitives for FlowForge."""

import time
import asyncio
from typing import List, Dict, Any, Union, Optional

def if_node(condition: str, then_step: str, else_step: str = None, **kwargs) -> dict:
    """
    Branch based on a boolean expression.
    
    Args:
        condition: Boolean expression as string
        then_step: Step ID to execute if condition is true
        else_step: Optional step ID to execute if condition is false
        **kwargs: Variables to be used in the condition evaluation
        
    Returns:
        Dictionary with the result of condition evaluation
    """
    # Create safe execution environment (no builtins)
    safe_globals = {"__builtins__": {}}
    
    # Evaluate the condition using any provided variables
    try:
        # If the condition is a direct reference (no operators), just check truthiness
        if condition in kwargs:
            result = bool(kwargs[condition])
        else:
            # Otherwise evaluate the expression with the kwargs as locals
            result = bool(eval(condition, safe_globals, kwargs))
    except Exception as e:
        raise ValueError(f"Error evaluating condition '{condition}': {str(e)}")
        
    return {"result": result}


def switch(value, cases: dict, default=None, **kwargs) -> dict:
    """
    Route by matching a value against cases.
    
    Args:
        value: Value to match against cases (can be a variable reference)
        cases: Dictionary mapping values to step IDs
        default: Optional default step ID if no case matches
        **kwargs: Variables to be used in case evaluation
        
    Returns:
        Dictionary with the matched case
    """
    # Check if value is a string reference to a variable
    actual_value = kwargs.get(value, value)
    
    # Get the matched step, or default if no match
    matched_case = cases.get(actual_value, default)
    return {"matched_case": matched_case}


def for_each(list_input, iterator_name: str, subflow: list, **kwargs) -> dict:
    """
    Iterate over a list, running a subflow per item.
    
    Args:
        list_input: List of items to iterate over (or reference to a list variable)
        iterator_name: Name of the variable to bind each item to
        subflow: List of step IDs to execute for each item
        **kwargs: Variables containing values that might be referenced
        
    Returns:
        Dictionary with results from each iteration
    """
    # Resolve list_input if it's a reference
    actual_list = kwargs.get(list_input, list_input) if isinstance(list_input, str) else list_input
    
    # Ensure we have an iterable
    if not isinstance(actual_list, (list, tuple, set)):
        try:
            actual_list = list(actual_list)
        except Exception:
            raise ValueError(f"Could not convert '{list_input}' to a list for iteration")
    
    # Return a placeholder result since actual execution happens at the flow engine level
    return {"results": [{"iteration": i, iterator_name: item} for i, item in enumerate(actual_list)]}


def while_loop(condition: str, subflow: Union[list, str], max_iterations: int = 100, **kwargs) -> dict:
    """
    Define a while loop structure to be executed by the flow engine.
    
    Note: This function doesn't actually execute the subflow - that's handled by the flow engine.
    It simply defines the loop structure and validates the condition.
    
    Args:
        condition: Boolean expression as string
        subflow: List of step IDs or objects to execute in each iteration
        max_iterations: Maximum number of iterations to prevent infinite loops
        **kwargs: Variables to be used in the condition evaluation
        
    Returns:
        Dictionary with information about the loop structure
    """
    # Initial condition check
    safe_globals = {"__builtins__": {}}
    
    try:
        # Check if condition is directly a variable name or an expression
        if condition in kwargs:
            # If it's just a variable name, get its boolean value
            initial_result = bool(kwargs[condition])
        else:
            # Otherwise evaluate as an expression
            initial_result = bool(eval(condition, safe_globals, kwargs))
    except Exception as e:
        raise ValueError(f"Error evaluating loop condition '{condition}': {str(e)}")

    # Return a description of the loop - actual execution happens in the flow engine
    return {
        "condition": condition,
        "subflow": subflow,
        "max_iterations": max_iterations,
        "condition_vars": list(kwargs.keys()),
        "initial_condition_result": initial_result,
        "next_step": subflow[0]["id"] if isinstance(subflow, list) and isinstance(subflow[0], dict) else subflow[0] if isinstance(subflow, list) else subflow,
    }

def parallel(branches: list, wait_for_all: bool = True, **kwargs) -> dict:
    """
    Run multiple subflows concurrently.
    
    Args:
        branches: List of lists of step IDs to execute in parallel
        wait_for_all: Whether to wait for all branches to complete
        **kwargs: Variables that might be referenced
        
    Returns:
        Dictionary with outputs from each branch
    """
    # Resolve branches if it's a reference
    actual_branches = kwargs.get(branches, branches) if isinstance(branches, str) else branches
    
    # Stub implementation - in real code this would spawn parallel tasks
    return {"branch_outputs": [{"branch": i} for i in range(len(actual_branches))]}


def merge(inputs: Union[list, str], strategy: str = "concat", **kwargs) -> dict:
    """
    Join parallel branches into a single flow.
    
    Args:
        inputs: List of inputs to merge, or reference to a list
        strategy: Strategy to use for merging (concat, first, last, etc.)
        **kwargs: Variables that might be referenced
        
    Returns:
        Dictionary with merged result
    """
    # Resolve inputs if it's a reference
    actual_inputs = kwargs.get(inputs, inputs) if isinstance(inputs, str) else inputs
    
    if not isinstance(actual_inputs, (list, tuple)):
        # Try to convert to list if possible
        try:
            actual_inputs = list(actual_inputs)
        except:
            actual_inputs = [actual_inputs]
    
    if strategy == "concat":
        if all(isinstance(x, list) for x in actual_inputs):
            merged = sum(actual_inputs, [])
        else:
            merged = actual_inputs
    elif strategy == "first":
        merged = actual_inputs[0] if actual_inputs else None
    elif strategy == "last":
        merged = actual_inputs[-1] if actual_inputs else None
    else:
        merged = actual_inputs
        
    return {"merged": merged}


def delay(seconds: Union[float, str], **kwargs) -> dict:
    """
    Pause execution for a fixed duration.
    
    Args:
        seconds: Number of seconds to pause, or reference to a value
        **kwargs: Variables that might be referenced
        
    Returns:
        Dictionary indicating completion
    """
    # Resolve seconds if it's a reference
    actual_seconds = kwargs.get(seconds, seconds) if isinstance(seconds, str) else seconds
    
    try:
        actual_seconds = float(actual_seconds)
    except ValueError:
        raise ValueError(f"Invalid delay duration: {seconds}")
    
    # In real implementation, this would use time.sleep or asyncio.sleep
    # Here we just return immediately
    return {"done": True, "seconds": actual_seconds}


def wait_for(until: str, timeout: Optional[Union[float, str]] = None, **kwargs) -> dict:
    """
    Wait until a timestamp or external event.
    
    Args:
        until: Timestamp or event identifier, or reference to a value
        timeout: Optional timeout in seconds, or reference to a value
        **kwargs: Variables that might be referenced
        
    Returns:
        Dictionary indicating whether the wait was triggered
    """
    # Resolve values if they're references
    actual_until = kwargs.get(until, until) if isinstance(until, str) else until
    actual_timeout = kwargs.get(timeout, timeout) if isinstance(timeout, str) else timeout
    
    if actual_timeout is not None:
        try:
            actual_timeout = float(actual_timeout)
        except ValueError:
            raise ValueError(f"Invalid timeout value: {timeout}")
    
    # Stub implementation - would be replaced with real waiting logic
    return {"triggered": True, "until": actual_until, "timeout": actual_timeout}


def try_catch(subflow: Union[list, str], on_error: Optional[Union[list, str]] = None, **kwargs) -> dict:
    """
    Execute subflow, catching any errors.
    
    Args:
        subflow: List of step IDs to execute, or reference to a list
        on_error: Optional list of step IDs to execute if an error occurs, or reference
        **kwargs: Variables that might be referenced
        
    Returns:
        Dictionary with success status and error information
    """
    # Resolve references if needed
    actual_subflow = kwargs.get(subflow, subflow) if isinstance(subflow, str) else subflow
    actual_on_error = kwargs.get(on_error, on_error) if isinstance(on_error, str) else on_error
    
    # Simulate successful execution
    return {
        "success": True, 
        "error": None, 
        "subflow": actual_subflow, 
        "on_error": actual_on_error
    }


def retry(action_step, attempts: Union[int, str] = 3, backoff_seconds: Union[float, str] = 0, **kwargs) -> dict:
    """
    Execute an action or subflow, retrying on failure.
    
    Args:
        action_step: Action or step to retry, or reference
        attempts: Maximum number of attempts, or reference to a value
        backoff_seconds: Seconds to wait between attempts, or reference
        **kwargs: Variables that might be referenced
        
    Returns:
        Dictionary with output from the action and attempts made
    """
    # Resolve references if needed
    actual_attempts = kwargs.get(attempts, attempts) if isinstance(attempts, str) else attempts
    actual_backoff = kwargs.get(backoff_seconds, backoff_seconds) if isinstance(backoff_seconds, str) else backoff_seconds
    
    try:
        actual_attempts = int(actual_attempts)
    except ValueError:
        raise ValueError(f"Invalid number of attempts: {attempts}")
        
    try:
        actual_backoff = float(actual_backoff)
    except ValueError:
        raise ValueError(f"Invalid backoff duration: {backoff_seconds}")
    
    # Simulate successful execution on first attempt
    return {
        "output": {}, 
        "attempts_made": 1, 
        "max_attempts": actual_attempts, 
        "backoff_seconds": actual_backoff
    }


def subflow(flow_id: str, inputs: Optional[Dict[str, Any]] = None, **kwargs) -> dict:
    """
    Call another flow by ID, passing inputs.
    
    Args:
        flow_id: ID of the flow to call, or reference to a value
        inputs: Optional inputs to pass to the flow, or reference
        **kwargs: Variables that might be referenced
        
    Returns:
        Dictionary with the result from the subflow
    """
    # Resolve references if needed
    actual_flow_id = kwargs.get(flow_id, flow_id) if isinstance(flow_id, str) else flow_id
    actual_inputs = kwargs.get(inputs, inputs) if isinstance(inputs, str) else inputs
    
    # Stub implementation - would execute the referenced flow
    return {"result": {}, "flow_id": actual_flow_id, "inputs": actual_inputs}


def terminate(message: Optional[str] = None, **kwargs) -> dict:
    """
    Halt execution immediately.
    
    Args:
        message: Optional message describing why execution was halted, or reference
        **kwargs: Variables that might be referenced
        
    Returns:
        Dictionary indicating halted status
    """
    # Resolve message if it's a reference
    actual_message = kwargs.get(message, message) if isinstance(message, str) else message
    
    return {"halted": True, "message": actual_message}