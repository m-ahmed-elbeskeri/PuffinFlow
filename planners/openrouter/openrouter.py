"""OpenRouter integration for FlowForge with improved YAML handling."""

import os
import requests
import json
import yaml
import re
from pathlib import Path

# Explicitly define the class at module level for proper import
class OpenRouterAPI:
    """API client for OpenRouter with improved YAML handling."""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key is required. Set the OPENROUTER_API_KEY environment variable.")
        
        self.base_url = "https://openrouter.ai/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.debug_mode = os.environ.get("FLOWFORGE_DEBUG", "0") == "1"
    
    def generate(self, prompt, model="anthropic/claude-3.5-sonnet", temperature=0.7, max_tokens=1024):
        """
        Generate content using OpenRouter.
        
        Args:
            prompt: The prompt to send to the model
            model: The model to use
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            
        Returns:
            Dictionary with the response
        """
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if self.debug_mode:
            print(f"\nDEBUG - Sending request to OpenRouter API:")
            print(f"Model: {model}")
            print(f"Temperature: {temperature}")
            print(f"Max tokens: {max_tokens}")
            print(f"Prompt (first 100 chars): {prompt[:100]}...")
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if self.debug_mode:
                print(f"\nDEBUG - Received response from OpenRouter API:")
                print(f"Response status: {response.status_code}")
                print(f"Response keys: {list(result.keys())}")
            
            return {"response": result["choices"][0]["message"]["content"]}
        except Exception as e:
            print(f"Error calling OpenRouter API: {str(e)}")
            
            if self.debug_mode and 'response' in locals():
                print(f"\nDEBUG - Response content: {response.text}")
            
            return {"response": f"Error: {str(e)}"}

    def generate_structured(self, prompt, user_message, schema, model="anthropic/claude-3.5-sonnet", temperature=0.2, max_tokens=2048):
        """
        Try to generate structured output, falling back to regular generation with JSON extraction.
        
        Args:
            prompt: System prompt for the model
            user_message: User message to send
            schema: JSON Schema to enforce
            model: The model to use
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            
        Returns:
            String containing the structured output (JSON)
        """
        # First, try without structured output since it's more widely supported
        enhanced_prompt = f"""
{prompt}

IMPORTANT: You MUST respond with a valid JSON object following this exact schema:
{json.dumps(schema, indent=2)}

Do not include any explanation or text outside the JSON object.
"""
        
        regular_result = self.generate(
            prompt=f"{enhanced_prompt}\n\n{user_message}",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        response_text = regular_result["response"]
        
        # Try to extract JSON from the response
        extracted_json = self._extract_json(response_text)
        if extracted_json:
            return json.dumps(extracted_json)
            
        # If JSON extraction failed, return the raw response for further processing
        return response_text
    
    def _extract_json(self, text):
        """Extract JSON from text using multiple strategies."""
        # Strategy 1: Try direct JSON parsing
        try:
            return json.loads(text)
        except:
            pass
        
        # Strategy 2: Look for JSON in code blocks
        try:
            if "```json" in text:
                json_text = text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_text)
            elif "```" in text:
                json_text = text.split("```")[1].split("```")[0].strip()
                try:
                    return json.loads(json_text)
                except:
                    pass
        except:
            pass
        
        # Strategy 3: Find JSON-like content with regex
        import re
        try:
            json_pattern = r'\{[\s\S]*\}'
            match = re.search(json_pattern, text)
            if match:
                json_text = match.group(0)
                # Clean the matched text
                json_text = re.sub(r'"""([\s\S]*?)"""', r'"\1"', json_text)
                json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)
                json_text = json_text.replace("'", '"')
                return json.loads(json_text)
        except:
            pass
        
        return None

    def create_flow(self, request, available_integrations=None, output_format="json"):
        """
        Create a flow definition from a natural language request.
        
        Args:
            request: The natural language request
            available_integrations: List of available integrations
            output_format: Output format (json or yaml)
            
        Returns:
            Dictionary with flow definition, diagram, and code
        """
        available_integrations = available_integrations or ["basic", "prompts", "openrouter"]
        
        # Create a system prompt that instructs the model how to create a flow
        system_prompt = f"""
        You are a specialized AI that creates flow definitions for the FlowForge system.
        
        Available integrations: {', '.join(available_integrations)}
        
        Each integration has actions with inputs and outputs:
        
        - basic.add: Adds two numbers
          - Inputs: a (number), b (number)
          - Output: sum (number)
        
        - basic.multiply: Multiplies two numbers
          - Inputs: x (number), y (number)
          - Output: product (number)
        
        - prompts.ask: Asks the user for input (human-in-the-loop)
          - Inputs: question (string), type (string), options (array, optional), default (any, optional)
          - Output: answer (any)
        
        - openrouter.generate: Generates text using AI
          - Inputs: prompt (string), model (string, optional), temperature (number, optional), max_tokens (number, optional)
          - Output: response (string)
        
        Your task is to create a complete flow definition based on the user's request.
        
        YAML FLOW STRUCTURE EXAMPLE:
        ```yaml
        id: add_three_numbers
        steps:
          - id: get_num1
            action: prompts.ask
            inputs:
              question: "Enter the first number:"
              type: "number"
          
          - id: get_num2
            action: prompts.ask
            inputs:
              question: "Enter the second number:"
              type: "number"
          
          - id: get_num3
            action: prompts.ask
            inputs:
              question: "Enter the third number:"
              type: "number"
          
          - id: add1
            action: basic.add
            inputs:
              a: get_num1.answer
              b: get_num2.answer
          
          - id: add2
            action: basic.add
            inputs:
              a: add1.sum
              b: get_num3.answer
        ```
        
        RESPONSE FORMAT:
        Return a JSON object with these fields:
        - flow_definition: YAML string with the flow definition
        - mermaid_diagram: Mermaid diagram code
        - python_code: Python code that implements the flow
        - explanation: Brief explanation of how the flow works
        
        IMPORTANT: Output ONLY the JSON object, nothing else.
        """
        
        # Generate output
        try:
            schema = {
                "type": "object",
                "properties": {
                    "flow_definition": {
                        "type": "string",
                        "description": "YAML string with the flow definition"
                    },
                    "mermaid_diagram": {
                        "type": "string",
                        "description": "Mermaid diagram code"
                    },
                    "python_code": {
                        "type": "string",
                        "description": "Python code that implements the flow"
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Brief explanation of how the flow works"
                    }
                },
                "required": ["flow_definition", "mermaid_diagram", "python_code", "explanation"]
            }
            
            response = self.generate_structured(
                prompt=system_prompt,
                user_message=f"Create a flow for: {request}",
                schema=schema,
                model="anthropic/claude-3.5-sonnet"
            )
            
            # Parse the response
            try:
                # Try to parse as JSON
                if self.debug_mode:
                    print(f"\nDEBUG - Response to parse as JSON (first 200 chars):\n{response[:200]}...\n")
                
                # Try to extract JSON from text
                result = self._extract_json(response)
                if result:
                    # Process the flow_definition to remove markdown code block syntax
                    if "flow_definition" in result:
                        result["flow_definition"] = self._clean_yaml(result["flow_definition"])
                    
                    # Convert flow definition format if needed
                    if output_format == "yaml" and isinstance(result.get("flow_definition"), dict):
                        result["flow_definition"] = yaml.dump(
                            result["flow_definition"], 
                            default_flow_style=False
                        )
                    
                    return result
                else:
                    # Try to extract YAML directly if JSON parsing fails
                    yaml_flow = self._extract_yaml(response)
                    
                    if yaml_flow:
                        return {
                            "flow_definition": yaml_flow,
                            "mermaid_diagram": self._extract_mermaid(response) or "graph TD\n    Start[\"Start\"] --> End[\"End\"]",
                            "python_code": self._extract_python(response) or "def run_flow():\n    # Implementation missing\n    return {}",
                            "explanation": self._extract_explanation(response) or "Flow generated from user request."
                        }
                    else:
                        # Fallback to predefined response
                        return self._create_fallback_response(request)
            except Exception as e:
                if self.debug_mode:
                    print(f"DEBUG - JSON parsing error: {str(e)}")
                return self._create_fallback_response(request)
            
        except Exception as e:
            print(f"Error with flow generation: {str(e)}")
            return self._create_fallback_response(request)
    
    def _clean_yaml(self, yaml_text):
        """Remove markdown code block syntax from YAML."""
        # First, check if the text starts with backticks
        if yaml_text.startswith("```"):
            # Remove the opening line with backticks
            lines = yaml_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            
            # Remove the closing backticks if present
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            
            return "\n".join(lines)
        
        return yaml_text
    
    def _extract_yaml(self, text):
        """Extract YAML flow definition from text."""
        try:
            # Look for YAML in code blocks
            if "```yaml" in text:
                yaml_text = text.split("```yaml")[1].split("```")[0].strip()
                return yaml_text
            elif "```" in text and "id:" in text and "steps:" in text:
                for block in text.split("```"):
                    if "id:" in block and "steps:" in block:
                        return block.strip()
            
            # Look for patterns
            import re
            yaml_pattern = r'id:.*?\nsteps:[\s\S]*?(?=\n\n|\Z)'
            match = re.search(yaml_pattern, text)
            if match:
                return match.group(0)
        except Exception as e:
            if self.debug_mode:
                print(f"DEBUG - YAML extraction error: {str(e)}")
        
        return None
    
    def _extract_mermaid(self, text):
        """Extract Mermaid diagram from text."""
        try:
            if "```mermaid" in text:
                return text.split("```mermaid")[1].split("```")[0].strip()
            elif "graph TD" in text:
                import re
                mermaid_pattern = r'graph TD[\s\S]*?(?=\n\n|```|\Z)'
                match = re.search(mermaid_pattern, text)
                if match:
                    return match.group(0)
        except:
            pass
        
        return None
    
    def _extract_python(self, text):
        """Extract Python code from text."""
        try:
            if "```python" in text:
                return text.split("```python")[1].split("```")[0].strip()
            elif "```" in text and "def " in text and "run_flow" in text:
                for block in text.split("```"):
                    if "def " in block and "run_flow" in block:
                        return block.strip()
        except:
            pass
        
        return None
    
    def _extract_explanation(self, text):
        """Extract explanation from text."""
        try:
            import re
            patterns = [
                r'explanation["\s:]+([^"]+)',
                r'This flow\s+(.*?)(?=\n\n|\Z)',
                r'The flow\s+(.*?)(?=\n\n|\Z)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    return match.group(1).strip()
            
            # Just take any paragraph that seems explanatory
            paragraphs = text.split('\n\n')
            for p in paragraphs:
                if len(p.strip()) > 30 and not p.strip().startswith('```'):
                    return p.strip()
        except:
            pass
        
        return None
    
    def _create_fallback_response(self, request):
        """Create a fallback response when flow generation fails."""
        # Check if the request is about adding numbers
        add_numbers = any(term in request.lower() for term in ['add', 'sum', 'plus', 'addition'])
        
        if add_numbers:
            return {
                "flow_definition": """id: add_numbers_flow
steps:
  - id: get_num1
    action: prompts.ask
    inputs:
      question: "Enter the first number:"
      type: "number"
  
  - id: get_num2
    action: prompts.ask
    inputs:
      question: "Enter the second number:"
      type: "number"
  
  - id: add_result
    action: basic.add
    inputs:
      a: get_num1.answer
      b: get_num2.answer
  
  - id: display
    action: prompts.ask
    inputs:
      question: "The sum is {{add_result.sum}}"
      type: "text"
      default: "Press Enter to continue"
""",
                "mermaid_diagram": "graph TD\n    get_num1[\"Get First Number\"] --> add_result\n    get_num2[\"Get Second Number\"] --> add_result\n    add_result[\"Add Numbers\"] --> display\n    display[\"Display Result\"]",
                "python_code": "def run_flow():\n    # Get user input\n    num1 = float(input(\"Enter the first number: \"))\n    num2 = float(input(\"Enter the second number: \"))\n    \n    # Calculate sum\n    result = num1 + num2\n    \n    # Display result\n    print(f\"The sum is {result}\")\n    input(\"Press Enter to continue...\")\n    \n    return {\"result\": result}",
                "explanation": "A simple flow that asks for two numbers, adds them together, and displays the result."
            }
        else:
            return {
                "flow_definition": """id: basic_flow
steps:
  - id: user_input
    action: prompts.ask
    inputs:
      question: "Please enter a value:"
      type: "text"
  
  - id: process
    action: openrouter.generate
    inputs:
      prompt: "Process this input: {{user_input.answer}}"
      temperature: 0.7
  
  - id: display
    action: prompts.ask
    inputs:
      question: "Result: {{process.response}}"
      type: "text"
      default: "Press Enter to continue"
""",
                "mermaid_diagram": "graph TD\n    user_input[\"Get User Input\"] --> process\n    process[\"Process Input\"] --> display\n    display[\"Display Result\"]",
                "python_code": "def run_flow():\n    # Get user input\n    user_input = input(\"Please enter a value: \")\n    \n    # Process the input (simplified)\n    result = f\"Processed: {user_input}\"\n    \n    # Display result\n    print(f\"Result: {result}\")\n    input(\"Press Enter to continue...\")\n    \n    return {\"result\": result}",
                "explanation": "A basic flow that takes user input, processes it, and displays the result."
            }

# Module functions for registry
def generate(prompt, model="anthropic/claude-3.5-sonnet", temperature=0.7, max_tokens=1024):
    """
    Generate text using OpenRouter.
    
    Args:
        prompt: The prompt to send to the model
        model: The model to use
        temperature: Temperature for generation
        max_tokens: Maximum tokens to generate
        
    Returns:
        Dictionary with the response
    """
    api = OpenRouterAPI()
    return api.generate(prompt, model, temperature, max_tokens)

def create_flow(request, available_integrations=None, output_format="json"):
    """
    Create a flow definition from a natural language request.
    
    Args:
        request: The natural language request
        available_integrations: List of available integrations
        output_format: Output format (json or yaml)
        
    Returns:
        Dictionary with flow definition, diagram, and code
    """
    api = OpenRouterAPI()
    return api.create_flow(request, available_integrations, output_format)