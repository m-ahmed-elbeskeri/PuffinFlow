
"""Module with multiplication functionality for the basic integration."""

def multiply(x: float, y: float) -> dict:
    """
    Multiply two numbers.
    
    Args:
        x: First number
        y: Second number
        
    Returns:
        Dictionary with the product
    """
    # Convert inputs to float if they're strings
    if isinstance(x, str):
        x = float(x)
    if isinstance(y, str):
        y = float(y)
        
    return {"product": x * y}