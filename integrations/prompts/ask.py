"""Interactive input handling module for the prompts integration."""

def ask(question, type="text", options=None, default=None):
    """
    Ask the user for input with a specific question and type.
    
    Args:
        question: The question to ask
        type: Type of input (text, select, confirm, number)
        options: List of options for select inputs
        default: Default value
        
    Returns:
        Dictionary containing the user's answer
    """
    if not options:
        options = []
        
    # Display the question
    print(f"\n{question}")
    
    # Handle different input types
    if type == "select" and options:
        # Display options with numbers
        for i, option in enumerate(options):
            print(f"{i+1}. {option}")
            
        # Get user selection
        while True:
            choice = input(f"Select an option (1-{len(options)}) [default: {default or '1'}]: ")
                
            # Use default if empty
            if not choice and default is not None:
                return {"answer": default}
            elif not choice:
                return {"answer": options[0]}
                
            try:
                index = int(choice) - 1
                if 0 <= index < len(options):
                    return {"answer": options[index]}
                else:
                    print(f"Please enter a number between 1 and {len(options)}")
            except ValueError:
                print("Please enter a valid number")
    
    elif type == "confirm":
        # Yes/no question
        while True:
            choice = input(f"(y/n) [default: {default or 'y'}]: ").lower()
                
            # Use default if empty
            if not choice and default is not None:
                return {"answer": default}
            elif not choice:
                return {"answer": True}
                
            if choice in ["y", "yes", "true"]:
                return {"answer": True}
            elif choice in ["n", "no", "false"]:
                return {"answer": False}
            else:
                print("Please enter 'y' or 'n'")
    
    elif type == "number":
        # Numeric input
        while True:
            value = input(f"Enter a number [default: {default or '0'}]: ")
                
            # Use default if empty
            if not value and default is not None:
                return {"answer": default}
            elif not value:
                return {"answer": 0}
                
            try:
                return {"answer": float(value)}
            except ValueError:
                print("Please enter a valid number")
    
    else:
        # Default to text input
        value = input(f"[default: {default or ''}]: ")
            
        # Use default if empty
        if not value and default is not None:
            return {"answer": default}
            
        return {"answer": value}