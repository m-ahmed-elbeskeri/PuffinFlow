"""Interactive flow generator with improved variables handling."""

import os
import json
import yaml
import re
from pathlib import Path

class InteractiveFlowGenerator:
    """Generate flows with human-in-the-loop clarification and improved variable handling."""
    
    def __init__(self, openrouter_api, registry):
        """
        Initialize the interactive flow generator.
        
        Args:
            openrouter_api: OpenRouterAPI instance
            registry: Registry instance with available integrations
        """
        self.api = openrouter_api
        self.registry = registry
        self.conversation_history = []
        self.clarifications = {}
        self.debug_mode = os.environ.get("FLOWFORGE_DEBUG", "0") == "1"
        self.detected_variables = {
            'env': set(),    # Environment variables 
            'local': set()   # Local flow variables
        }
    
    def _format_integration_details(self):
        """
        Format integration details in a structured way for the model prompt.
        
        Returns:
            String with detailed information about all available integrations and their actions
        """
        formatted_details = []
        
        # Iterate through all integrations in the registry
        for integration_name, integration_data in self.registry.integrations.items():
            # Start with the integration name
            integration_section = [f"- {integration_name}: {integration_data.get('description', 'No description available')}"]
            
            # Add actions for this integration
            actions = integration_data.get('actions', {})
            for action_name, action_data in actions.items():
                # Format full action name and description
                action_full_name = f"{integration_name}.{action_name}"
                action_desc = action_data.get('description', 'No description available')
                integration_section.append(f"  - {action_full_name}: {action_desc}")
                
                # Add inputs for this action
                if 'inputs' in action_data:
                    integration_section.append("    - Inputs:")
                    for input_name, input_data in action_data['inputs'].items():
                        # Check if input_data is a dictionary (as it should be)
                        if isinstance(input_data, dict):
                            input_type = input_data.get('type', 'any')
                            required = input_data.get('required', False)
                            desc = input_data.get('description', '')
                            req_text = "required" if required else "optional"
                            
                            # Add examples if they exist
                            example_text = ""
                            if 'examples' in input_data and input_data['examples']:
                                examples = input_data['examples']
                                if isinstance(examples, list) and len(examples) > 0:
                                    example_text = f" (Example: '{examples[0]}')"
                                    
                            integration_section.append(f"      - {input_name} ({input_type}, {req_text}): {desc}{example_text}")
                        else:
                            # Fallback if input_data is not a dictionary
                            integration_section.append(f"      - {input_name}")
                
                # Add outputs for this action
                if 'outputs' in action_data:
                    integration_section.append("    - Outputs:")
                    for output_name, output_type in action_data['outputs'].items():
                        # Handle output if it's a string or a dictionary
                        if isinstance(output_type, dict):
                            output_type_str = output_type.get('type', 'any')
                            desc = output_type.get('description', '')
                            integration_section.append(f"      - {output_name} ({output_type_str}): {desc}")
                        else:
                            integration_section.append(f"      - {output_name} ({output_type})")
            
            # Add this integration section to the overall details
            formatted_details.append("\n".join(integration_section))
        
        # Combine all integration details
        return "\n\n".join(formatted_details)
    
    def analyze_request(self, request):
        """
        Analyze a user request to identify missing information or ambiguities.
        
        Args:
            request: User's natural language request
            
        Returns:
            Dictionary with analysis results
        """
        # Get formatted integration details
        integration_details = self._format_integration_details()
        
        # Create a system prompt for analyzing the request
        system_prompt = f"""
        You are an AI assistant that analyzes requests for a flow building system called FlowForge.
        
        AVAILABLE INTEGRATIONS AND ACTIONS:
        {integration_details}
        
        VARIABLE SYSTEM:
        FlowForge has a robust variable system with two types of variables:
        1. Environment variables - accessed with {{env.VARIABLE_NAME}} or variables.get_env
        2. Local flow variables - accessed with {{variable_name}} or {{var.variable_name}} or variables.set_local/get_local
        
        When identifying variables in the user's request, categorize them as either environment variables
        (typically API keys, credentials, system paths) or local flow variables (counters, user inputs, 
        intermediate values).
        
        TASK:
        Analyze the user's request and identify any missing information or ambiguities that would need clarification before generating a complete flow.
        
        IMPORTANT:
        Return your analysis as a JSON object with these fields:
        - clear_enough: true/false indicating if the request has enough information
        - missing_information: array of specific pieces of missing information
        - clarification_questions: array of specific questions to ask the user
        - suggested_flow_description: brief description of what the flow would do
        - suggested_variables: object with two fields:
          - environment: array of suggested environment variable names (like API_KEY, AUTH_TOKEN)
          - local: array of suggested local variable names (like counter, total, user_name)
        
        Example output format:
        {{
            "clear_enough": false,
            "missing_information": ["operation to perform with numbers", "output format"],
            "clarification_questions": [
                "What operation do you want to perform with the numbers?",
                "How would you like to see the output of the calculation?"
            ],
            "suggested_flow_description": "A flow to perform mathematical operations on user-provided numbers",
            "suggested_variables": {{
                "environment": ["API_KEY"],
                "local": ["counter", "total"]
            }}
        }}
        
        Return ONLY the JSON object, nothing else. Do not include any explanations or other text.
        """
        
        # Add request to conversation history
        self.conversation_history.append({"role": "user", "content": request})
        
        try:
            # Generate analysis
            response = self.api.generate(
                prompt=f"{system_prompt}\n\nUser request: {request}",
                temperature=0.3,
                max_tokens=1024
            )
            
            # Log the raw response if debugging is enabled
            if self.debug_mode:
                print(f"\nDEBUG - Raw analysis response:\n{response}\n")
            
            # Try to extract JSON from response
            try:
                response_text = response["response"]
                analysis = self._extract_json(response_text)
                
                if not analysis or not all(key in analysis for key in ["clear_enough", "clarification_questions", "suggested_flow_description"]):
                    raise ValueError("Invalid analysis format")
                
                # Add analysis to conversation history
                self.conversation_history.append({"role": "assistant", "content": f"Analysis: {json.dumps(analysis)}"})
                
                # Track detected variables
                suggested_vars = analysis.get('suggested_variables', {})
                self.detected_variables['env'].update(suggested_vars.get('environment', []))
                self.detected_variables['local'].update(suggested_vars.get('local', []))
                
                return analysis
            except Exception as e:
                if self.debug_mode:
                    print(f"DEBUG - Analysis parsing error: {str(e)}")
                # Default analysis as fallback
                return self._create_default_analysis()
                
        except Exception as e:
            print(f"Error generating analysis: {str(e)}")
            return self._create_default_analysis()
    
    def _extract_json(self, text):
        """Extract JSON from text using multiple strategies."""
        # Clean the text before any parsing attempts
        text = text.strip()
        
        # Log the input if in debug mode
        if self.debug_mode:
            print(f"DEBUG - Attempting to extract JSON from input (first 200 chars):\n{text[:200]}")
        
        # Strategy 1: Try direct JSON parsing on the entire text
        try:
            if self.debug_mode:
                print("Attempting direct JSON parsing...")
            
            # First try the raw text
            result = json.loads(text)
            if self.debug_mode:
                print("Successfully parsed JSON directly!")
            return result
        except Exception as e:
            if self.debug_mode:
                print(f"Direct JSON parsing failed: {str(e)}")
        
        # Strategy 2: Look for JSON in code blocks
        try:
            if self.debug_mode:
                print("Looking for JSON in code blocks...")
            
            # Check for JSON code blocks
            if "```json" in text:
                json_text = text.split("```json")[1].split("```")[0].strip()
                if self.debug_mode:
                    print(f"Found JSON block (first 50 chars): {json_text[:50]}...")
                return json.loads(json_text)
            
            # Check for any code blocks that might contain JSON
            elif "```" in text:
                for block in text.split("```"):
                    # Skip empty blocks
                    if not block.strip():
                        continue
                        
                    # Try to parse each block
                    try:
                        if self.debug_mode:
                            print(f"Trying code block (first 50 chars): {block[:50]}...")
                        result = json.loads(block.strip())
                        if self.debug_mode:
                            print("Successfully parsed JSON from code block!")
                        return result
                    except:
                        # Continue to next block if this one fails
                        pass
        except Exception as e:
            if self.debug_mode:
                print(f"JSON code block extraction failed: {str(e)}")
        
        # Strategy 3: Find JSON-like content with regex
        try:
            if self.debug_mode:
                print("Attempting regex-based JSON extraction...")
            
            # Find content that looks like complete JSON objects
            json_pattern = r'(\{[\s\S]*?\})'
            matches = re.finditer(json_pattern, text)
            
            for match in matches:
                json_text = match.group(0)
                
                # Clean the matched text
                json_text = re.sub(r'"""([\s\S]*?)"""', r'"\1"', json_text)
                json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)
                json_text = json_text.replace("'", '"')
                
                # Try to parse the JSON
                try:
                    if self.debug_mode:
                        print(f"Trying JSON-like content (first 50 chars): {json_text[:50]}...")
                    
                    parsed_json = json.loads(json_text)
                    
                    # Check if this looks like a valid analysis result
                    if all(k in parsed_json for k in ["clear_enough", "missing_information", "clarification_questions"]):
                        if self.debug_mode:
                            print("Found valid analysis result!")
                        return parsed_json
                    
                    # If it has some of the keys, it might be a partial match
                    if any(k in parsed_json for k in ["clear_enough", "missing_information", "clarification_questions"]):
                        if self.debug_mode:
                            print("Found partial analysis result - filling in missing fields")
                        
                        # Fill in any missing fields with defaults
                        result = {
                            "clear_enough": parsed_json.get("clear_enough", False),
                            "missing_information": parsed_json.get("missing_information", ["Unable to extract complete analysis"]),
                            "clarification_questions": parsed_json.get("clarification_questions", ["Could you please provide more details about your request?"]),
                            "suggested_flow_description": parsed_json.get("suggested_flow_description", "Flow based on user request"),
                            "suggested_variables": parsed_json.get("suggested_variables", {"environment": [], "local": []})
                        }
                        return result
                except Exception as e:
                    if self.debug_mode:
                        print(f"Failed to parse regex-matched JSON: {str(e)}")
        except Exception as e:
            if self.debug_mode:
                print(f"Regex JSON extraction failed: {str(e)}")
        
        # If we get here, all JSON extraction methods failed
        if self.debug_mode:
            print("All JSON extraction methods failed. Creating default analysis.")
        
        # Create a default analysis
        return self._create_default_analysis()
    
    def _create_default_analysis(self):
        """Create a default analysis as fallback."""
        return {
            "clear_enough": False,
            "missing_information": ["Unable to analyze request"],
            "clarification_questions": [
                "Could you please tell me if you want to get numbers from user input or from another source?",
                "When the sum exceeds 10, what would you like the flow to do next?"
            ],
            "suggested_flow_description": "A flow that adds numbers until the sum exceeds 10",
            "suggested_variables": {
                "environment": [],
                "local": ["counter", "total"]
            }
        }
    
    def ask_clarifying_questions(self, analysis):
        """
        Ask the user clarifying questions based on analysis.
        
        Args:
            analysis: Analysis results from analyze_request
            
        Returns:
            Dictionary with user's answers
        """
        answers = {}
        
        if not analysis.get("clear_enough", True):
            print("\nSuggested flow: " + analysis.get("suggested_flow_description", "No description available"))
            
            # Show suggested variables if any were detected
            suggested_vars = analysis.get("suggested_variables", {})
            env_vars = suggested_vars.get("environment", [])
            local_vars = suggested_vars.get("local", [])
            
            if env_vars:
                print("\nSuggested Environment Variables:")
                for var in env_vars:
                    print(f"  - {var}")
                    # Track detected variables
                    self.detected_variables['env'].add(var)
            
            if local_vars:
                print("\nSuggested Local Variables:")
                for var in local_vars:
                    print(f"  - {var}")
                    # Track detected variables
                    self.detected_variables['local'].add(var)
            
            print("\nI need some clarification before creating your flow:")
            
            for i, question in enumerate(analysis.get("clarification_questions", [])):
                print(f"\n{question}")
                answer = input("> ")
                
                # Add to conversation history
                self.conversation_history.append({"role": "assistant", "content": question})
                self.conversation_history.append({"role": "user", "content": answer})
                
                # Store answer
                question_key = f"clarification_{i+1}"
                answers[question_key] = answer
                self.clarifications[question_key] = {
                    "question": question,
                    "answer": answer
                }
                
                # Check for variable mentions in the answer
                self._detect_variables_in_text(answer)
        
        return answers
    
    def _detect_variables_in_text(self, text):
        """
        Detect potential variable names in text.
        
        Args:
            text: Text to analyze for variable names
        """
        # Environment variable patterns (uppercase with underscores)
        env_var_pattern = r'\b([A-Z][A-Z0-9_]*)\b'
        env_matches = re.findall(env_var_pattern, text)
        
        # Filter out common words that are all caps but not likely variables
        non_var_words = {"OK", "YES", "NO", "TRUE", "FALSE", "AND", "OR", "IF", "THEN", "ELSE"}
        env_vars = [word for word in env_matches if word not in non_var_words and len(word) > 1]
        
        # Local variable patterns (lowercase/camelCase with underscores)
        local_var_pattern = r'\b([a-z][a-zA-Z0-9_]*)\b'
        local_matches = re.findall(local_var_pattern, text)
        
        # Filter out common words that are likely not variables
        common_words = {"if", "else", "then", "and", "or", "the", "to", "from", "a", "an", "in", "of", "for", "with"}
        local_vars = [word for word in local_matches if word not in common_words and len(word) > 1]
        
        # Add detected variables to our sets
        self.detected_variables['env'].update(env_vars)
        self.detected_variables['local'].update(local_vars)
    
    def generate_flow(self, request, answers=None):
        """
        Generate a flow with clarifications.
        
        Args:
            request: Original user request
            answers: Optional answers to clarifying questions
            
        Returns:
            Dictionary with flow definition
        """
        # Get formatted integration details
        integration_details = self._format_integration_details()
        
        # Prepare environment and local variable lists for the prompt
        env_vars_list = ", ".join(sorted(self.detected_variables['env']))
        local_vars_list = ", ".join(sorted(self.detected_variables['local']))
        
        # Create a system prompt with better guidance on variables and control flow
        system_prompt = f"""
        You are a specialized AI that creates flow definitions for the FlowForge system.
        
        AVAILABLE INTEGRATIONS AND ACTIONS:
        {integration_details}

        DETECTED VARIABLES:
        Environment Variables: {env_vars_list or "None detected"}
        Local Flow Variables: {local_vars_list or "None detected"}
        
        VARIABLE SYSTEM GUIDELINES:
        - For environment variables (like API keys, credentials):
          - Use variables.get_env to retrieve values
          - Reference in strings with {{env.VARIABLE_NAME}}
          - Always use UPPERCASE_WITH_UNDERSCORES naming
        
        - For local flow variables:
          - Use variables.set_local to store values
          - Use variables.get_local to retrieve values
          - Reference directly in templates as {{variable_name}} or with {{var.variable_name}}
          - Always use camelCase or snake_case for local variables
        
        TASK:
        Create a complete YAML flow definition based on the user's request and their answers to clarifying questions.
        
        IMPORTANT CONDITION FORMATTING:
        - For control flow conditions, ALWAYS pass variables as additional inputs and use the variable name in the condition:
          EXAMPLE - Correct:
            action: control.if_node
            inputs:
              condition: "a > 10"
              a: some_step.output
              then_step: next_step_true
              else_step: next_step_false
          
          EXAMPLE - Incorrect (will cause eval error):
            action: control.if_node
            inputs:
              condition: "some_step.output > 10"
              then_step: next_step_true
              else_step: next_step_false
        
        - For while loops, follow the same pattern:
          EXAMPLE - Correct:
            action: control.while_loop
            inputs:
              condition: "total < max_value"  
              total: running_total.value
              max_value: 100
              subflow: [step1, step2]
        
        GENERAL TEMPLATING RULES:
        - For variable interpolation in strings, use DOUBLE curly braces: {{{{variable_name}}}}
        - For referencing step outputs, use format: step_id.output_name (e.g., add_numbers.sum)
        - For string values that contain expressions or special characters, always use quotes
        - EXAMPLE of correct templating: "The sum of {{{{get_first.answer}}}} and {{{{get_second.answer}}}} is {{{{add_numbers.sum}}}}"
        
        YAML FLOW STRUCTURE EXAMPLE:
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
          
          - id: check_sum
            action: control.if_node
            inputs:
              condition: "sum > 10"
              sum: add1.sum
              then_step: display_large
              else_step: add_more
          
          - id: add_more
            action: basic.add
            inputs:
              a: add1.sum
              b: get_num3.answer
              
          - id: display_large
            action: prompts.notify
            inputs:
              message: "The sum exceeds 10: {{{{add1.sum}}}}"
              level: "success"
          
          - id: display_final
            action: prompts.notify
            inputs:
              message: "The sum of the three numbers is {{{{add_more.sum}}}}"
              level: "success"
        
        RESPONSE FORMAT:
        Return ONLY the YAML flow definition without any additional content, markdown, or code blocks.
        """
        
        # Construct the user message including original request and clarifications
        user_message = f"Original request: {request}"
        
        # Add clarifications if available
        if self.clarifications:
            clarifications_text = "\n\nClarifications:\n"
            for key, value in self.clarifications.items():
                clarifications_text += f"- {value['question']}\n  Answer: {value['answer']}\n"
            user_message += clarifications_text
        
        try:
            print("Sending generation request to AI model...")
            
            # Generate the flow using regular generation
            response = self.api.generate(
                prompt=f"{system_prompt}\n\n{user_message}",
                temperature=0.2,
                max_tokens=2048
            )
            
            # Log the raw response if debugging is enabled
            if self.debug_mode:
                print(f"\nDEBUG - Raw flow generation response:\n{response['response']}\n")
            
            # Extract YAML directly
            yaml_content = self._extract_direct_yaml(response["response"])
            
            # Check for env variables in the generated flow
            if yaml_content:
                self._extract_variables_from_yaml(yaml_content)
            
            # Validate basic YAML structure
            if yaml_content and yaml_content.startswith("id:") and "steps:" in yaml_content:
                print("Successfully generated flow!")
                
                # Create a simplified result
                result = {
                    "flow_definition": yaml_content,
                    "raw_llm_response": response["response"]
                }
                
                # Generate diagram and code using codegen functions
                try:
                    import yaml as yaml_lib
                    from core import codegen
                    
                    flow_dict = yaml_lib.safe_load(yaml_content)
                    result["mermaid_diagram"] = codegen.generate_mermaid(flow_dict)
                    result["python_code"] = codegen.generate_python(flow_dict, self.registry)
                    result["explanation"] = self._extract_explanation(response["response"]) or "Flow generated from user request."
                    
                    # Generate .env file template if environment variables were found
                    if self.detected_variables['env']:
                        self._generate_env_template(flow_dict.get('id', 'flow'))
                except Exception as e:
                    if self.debug_mode:
                        print(f"DEBUG - Error generating diagram/code: {str(e)}")
                    # Continue without diagram/code if generation fails
                    pass
                    
                return result
                
            else:
                print("Error: Invalid YAML flow definition")
                print("Raw response first 200 characters:")
                print(response["response"][:200])
                
                # Try fallback extraction methods
                print("Attempting alternative extraction methods...")
                flow_yaml = self._extract_yaml(response["response"])
                
                if flow_yaml:
                    print("Successfully extracted YAML using fallback method")
                    
                    # Check for env variables in the extracted YAML
                    self._extract_variables_from_yaml(flow_yaml)
                    
                    result = {
                        "flow_definition": flow_yaml,
                        "raw_llm_response": response["response"]
                    }
                    
                    try:
                        # Generate .env file template if environment variables were found
                        if self.detected_variables['env']:
                            flow_id = re.search(r'id:\s*([^\n]+)', flow_yaml)
                            if flow_id:
                                self._generate_env_template(flow_id.group(1).strip())
                    except Exception as e:
                        if self.debug_mode:
                            print(f"DEBUG - Error generating .env template: {str(e)}")
                    
                    return result
                
                # Return error result if all extraction methods fail
                return {
                    "flow_definition": "id: error\n# Error: Invalid flow definition returned",
                    "raw_llm_response": response["response"]
                }
                    
        except Exception as e:
            error_msg = f"Error generating flow: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            
            return {
                "flow_definition": f"id: error\n# Error: {error_msg}",
                "raw_llm_response": "Exception occurred: " + str(e)
            }
    
    def _extract_direct_yaml(self, text):
        """Extract YAML directly with minimal processing."""
        # Clean up the text
        text = text.strip()
        
        # Remove markdown code blocks if present
        if "```yaml" in text:
            text = text.split("```yaml")[1].split("```")[0].strip()
        elif "```" in text and ("id:" in text or "steps:" in text):
            for block in text.split("```"):
                if "id:" in block and "steps:" in block:
                    text = block.strip()
                    break
        
        # Just extract from the start of id: to the end if possible
        if text.startswith("id:"):
            return text
        elif "id:" in text:
            return text[text.find("id:"):]
        
        # If we can't find a clean way to extract, return what we have
        return text
    
    def _clean_yaml(self, yaml_text):
        """Remove markdown code block syntax from YAML and fix templating syntax."""
        # First, check if the text contains markdown code block syntax
        if "```" in yaml_text:
            # Remove the opening line with backticks
            lines = yaml_text.split("\n")
            start_index = 0
            end_index = len(lines)
            
            for i, line in enumerate(lines):
                if line.strip().startswith("```") and i < end_index:
                    start_index = i + 1
                elif line.strip() == "```" and i > start_index:
                    end_index = i
                    break
            
            yaml_text = "\n".join(lines[start_index:end_index])
        
        # Fix templating syntax: replace ${...} with {{...}}
        yaml_text = re.sub(r'\${([^}]+)}', r'{{\1}}', yaml_text)
        
        return yaml_text
    
    def _extract_yaml(self, text):
        """Extract YAML flow definition from text."""
        try:
            # Look for YAML in code blocks
            if "```yaml" in text:
                yaml_text = text.split("```yaml")[1].split("```")[0].strip()
                print(f"Found YAML in code block (first 50 chars): {yaml_text[:50]}...")
                return yaml_text
            elif "```" in text and "id:" in text and "steps:" in text:
                for block in text.split("```"):
                    if "id:" in block and "steps:" in block:
                        print(f"Found YAML-like content in code block (first 50 chars): {block.strip()[:50]}...")
                        return block.strip()
            
            # Look for patterns
            yaml_pattern = r'id:.*?\nsteps:[\s\S]*?(?=\n\n|\Z)'
            match = re.search(yaml_pattern, text)
            if match:
                yaml_text = match.group(0)
                print(f"Found YAML-like content via regex (first 50 chars): {yaml_text[:50]}...")
                return yaml_text
            
            # Try yet another pattern - just find id: and grab everything after
            if "id:" in text:
                yaml_text = text[text.find("id:"):]
                print(f"Found YAML starting with 'id:' (first 50 chars): {yaml_text[:50]}...")
                return yaml_text
        except Exception as e:
            if self.debug_mode:
                print(f"DEBUG - YAML extraction error: {str(e)}")
            print(f"YAML extraction error: {str(e)}")
        
        print("All YAML extraction methods failed")
        return None
    
    def _extract_variables_from_yaml(self, yaml_text):
        """Extract environment and local variables from YAML content."""
        # Environment variable patterns:
        # 1. variables.get_env with name: "VAR_NAME"
        env_var_actions = re.findall(r'action:\s*variables\.get_env\b.*?name:\s*["\']([A-Z0-9_]+)["\']', yaml_text, re.DOTALL)
        self.detected_variables['env'].update(env_var_actions)
        
        # 2. {{env.VAR_NAME}} in string templates
        env_var_templates = re.findall(r'\{\{\s*env\.([A-Z0-9_]+)\s*\}\}', yaml_text)
        self.detected_variables['env'].update(env_var_templates)
        
        # Local variable patterns:
        # 1. variables.set_local with name: "var_name"
        local_var_actions = re.findall(r'action:\s*variables\.set_local\b.*?name:\s*["\']([a-zA-Z0-9_]+)["\']', yaml_text, re.DOTALL)
        self.detected_variables['local'].update(local_var_actions)
        
        # 2. variables.get_local with name: "var_name"
        local_var_gets = re.findall(r'action:\s*variables\.get_local\b.*?name:\s*["\']([a-zA-Z0-9_]+)["\']', yaml_text, re.DOTALL)
        self.detected_variables['local'].update(local_var_gets)
        
        # 3. {{var_name}} or {{var.var_name}} in string templates
        local_var_templates1 = re.findall(r'\{\{\s*([a-z][a-zA-Z0-9_]*)\s*\}\}', yaml_text)
        local_var_templates2 = re.findall(r'\{\{\s*var\.([a-z][a-zA-Z0-9_]*)\s*\}\}', yaml_text)
        self.detected_variables['local'].update(local_var_templates1)
        self.detected_variables['local'].update(local_var_templates2)
    
    def _generate_env_template(self, flow_id):
        """Generate a .env template file for the detected environment variables."""
        if not self.detected_variables['env']:
            return
        
        # Create env_files directory if it doesn't exist
        env_dir = Path("env_files")
        env_dir.mkdir(exist_ok=True)
        
        # Create .env file named after the flow
        env_file = env_dir / f"{flow_id}.env"
        
        # Generate content
        lines = [
            f"# Environment variables for flow: {flow_id}",
            "# Copy this file to .env and fill in the values",
            ""
        ]
        
        for var_name in sorted(self.detected_variables['env']):
            lines.append(f"{var_name}=")
        
        # Write the file
        with open(env_file, 'w') as f:
            f.write("\n".join(lines))
        
        print(f"Generated .env template file: {env_file}")
    
    def _extract_mermaid(self, text):
        """Extract Mermaid diagram from text."""
        try:
            if "```mermaid" in text:
                return text.split("```mermaid")[1].split("```")[0].strip()
            elif "graph TD" in text:
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