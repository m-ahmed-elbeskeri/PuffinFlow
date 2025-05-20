"""Module with addition functionality for the basic integration."""

def add(a: float, b: float) -> dict:
    """
    Add two numbers together.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        Dictionary with the sum
    """
    # Convert inputs to float if they're strings
    if isinstance(a, str):
        a = float(a)
    if isinstance(b, str):
        b = float(b)
        
    return {"sum": a + b}