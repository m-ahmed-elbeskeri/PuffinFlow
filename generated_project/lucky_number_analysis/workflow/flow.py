import os
import sys
from pathlib import Path

# Dynamic path resolution to find modules regardless of where project is copied
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
# Navigate up to the project root based on directory structure
PROJECT_ROOT = SCRIPT_DIR
# Look for the integrations folder at different levels
while PROJECT_ROOT.name and not (PROJECT_ROOT / 'integrations').exists():
    parent = PROJECT_ROOT.parent
    if parent == PROJECT_ROOT:  # Reached filesystem root
        break
    PROJECT_ROOT = parent
if not (PROJECT_ROOT / 'integrations').exists():
    # Fallback: Check if current directory has integrations
    if (Path.cwd() / 'integrations').exists():
        PROJECT_ROOT = Path.cwd()
# Add project root to system path if not already there
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.basic import add
from integrations.openai import chat
from integrations.prompts import ask
from integrations.prompts import notify

def run_flow():
    # Initialize flow variable storage
    flow_variables = {}

    # Step: get_first (prompts.ask)
    get_first_result = ask.ask(question='Enter the first number:', type='number')

    # Step: get_second (prompts.ask)
    get_second_result = ask.ask(question='Enter the second number:', type='number')

    # Step: get_third (prompts.ask)
    get_third_result = ask.ask(question='Enter the third number:', type='number')

    # Step: add_first_two (basic.add)
    add_first_two_result = add.add(a=get_first_result['answer'], b=get_second_result['answer'])

    # Step: add_final (basic.add)
    add_final_result = add.add(a=add_first_two_result['sum'], b=get_third_result['answer'])

    # Variable operation: store_sum (variables.set_local)
    flow_variables['sum'] = add_final_result['sum']
    store_sum_result = {'value': add_final_result['sum']}

    # Variable operation: create_prompt (variables.set_local)
    flow_variables['ai_response'] = f"The number {flow_variables.get('sum', '')} - is this number considered lucky or significant in any cultural or societal context? Please provide specific examples from different cultures and traditions if applicable."
    create_prompt_result = {'value': f"The number {flow_variables.get('sum', '')} - is this number considered lucky or significant in any cultural or societal context? Please provide specific examples from different cultures and traditions if applicable."}

    # Step: ask_ai (openai.chat_completion)
    ask_ai_result = chat.chat_completion(model='gpt-4-turbo-preview', prompt=flow_variables.get('ai_response', None), system_message='You are a cultural expert with deep knowledge of numerology, cultural significance of numbers, and lucky numbers across different societies. Please provide detailed, accurate information about the cultural significance of numbers.', temperature=0.7, max_tokens=500)

    # Step: display_result (prompts.notify)
    display_result_result = notify.notify(message=f"Sum: {flow_variables.get('sum', '')}\n\nAnalysis: {ask_ai_result['response']}", level='info')

    return display_result_result