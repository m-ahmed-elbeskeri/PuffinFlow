"""Flow execution script."""

from workflow.flow import run_flow
import json
import os
import sys

def main():
    """Execute the flow and return the result."""
    # Load .env file if it exists
    if os.path.exists(".env"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print("Loaded environment variables from .env file.")
        except ImportError:
            print("Warning: python-dotenv not installed. Environment variables from .env file will not be loaded.")
    elif os.path.exists("../.env"):
        try:
            from dotenv import load_dotenv
            load_dotenv("../.env")
            print("Loaded environment variables from ../.env file.")
        except ImportError:
            print("Warning: python-dotenv not installed. Environment variables from .env file will not be loaded.")
    
    try:
        print("Starting flow execution...")
        result = run_flow()
        
        print("\nFlow execution completed successfully!")
        print("=" * 50)
        
        # Try to make result JSON-serializable for display
        try:
            result_str = json.dumps(result, indent=2, default=str)
            print("Flow Result:")
            print(result_str)
        except (TypeError, ValueError):
            print(f"Flow Result (not JSON serializable): {result}")
            
        return result
        
    except KeyboardInterrupt:
        print("\nFlow execution interrupted by user.")
        return None
        
    except Exception as e:
        print(f"\nError executing flow: {type(e).__name__}: {str(e)}")
        
        # Print traceback in debug mode
        if os.environ.get("FLOWFORGE_DEBUG", "").lower() in ("1", "true", "yes"):
            import traceback
            print("\nFull traceback:")
            traceback.print_exc()
        else:
            print("\nFor detailed error information, set FLOWFORGE_DEBUG=1")
            
        return None

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result is not None else 1)
