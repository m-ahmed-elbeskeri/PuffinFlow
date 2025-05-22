from integrations.openai import chat
from integrations.openai import embedding
from integrations.openai import image
from integrations.openai import openai
from integrations.prompts import ask
from integrations.prompts import notify
from integrations.prompts import progress

def run_flow():
    # Step: get_first (prompts.ask)
    get_first = ask.ask(question='Enter the first number:', type='number')

    # Step: get_second (prompts.ask)
    get_second = ask.ask(question='Enter the second number:', type='number')

    # Step: get_third (prompts.ask)
    get_third = ask.ask(question='Enter the third number:', type='number')

    # Step: add_first_two (basic.add)
    add_first_two = get_first['answer'] + get_second['answer']

    # Step: add_final (basic.add)
    add_final = add_first_two + get_third['answer']

    # Step: store_sum (variables.set_local)
    sum = add_final

    # Step: create_prompt (variables.set_local)
    ai_response = f"The number {{sum}} - is this number considered lucky or significant in any cultural or societal context? Please provide specific examples from different cultures and traditions if applicable."

    # Step: ask_ai (openai.chat_completion)
    ask_ai = chat.chat_completion(model='gpt-4-turbo-preview', prompt='ai_response', system_message='You are a cultural expert with deep knowledge of numerology, cultural significance of numbers, and lucky numbers across different societies. Please provide detailed, accurate information about the cultural significance of numbers.', temperature=0.7, max_tokens=500)

    # Step: display_result (prompts.notify)
    display_result = notify.notify(message=f"""Sum: {{sum}}

Analysis: {ask_ai['response']}""", level='info')
    return display_result