"""Flow execution script."""

from workflow.flow import run_flow
import json

def main():
    """Execute the flow and return the result."""
    try:
        result = run_flow()
        
        # Try to make result JSON-serializable for display
        try:
            result_str = json.dumps(result, indent=2)
            print(f"Flow completed successfully. Result:")
            print(result_str)
        except (TypeError, ValueError):
            print(f"Flow completed successfully. Result: {result}")
            
        return result
    except Exception as e:
        print(f"Error executing flow: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()
