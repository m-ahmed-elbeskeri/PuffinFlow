"""OpenAI chat integration module for FlowForge."""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional, Union
from openai import OpenAI

# Import to get _get_openai_client function
from integrations.openai.openai import _get_openai_client

def chat_completion(
    prompt: str,
    system_message: Optional[str] = None,
    model: str = "gpt-4o",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    stop: Optional[List[str]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Generate a chat completion using OpenAI's chat models.
    
    Args:
        prompt: The prompt to send to the model
        system_message: Optional system message to set context for the chat
        model: The model to use for the completion (e.g., gpt-4o, gpt-3.5-turbo)
        temperature: Temperature for sampling (0-2)
        max_tokens: Maximum number of tokens to generate
        top_p: Top-p sampling value (0-1)
        frequency_penalty: Frequency penalty (-2 to 2)
        presence_penalty: Presence penalty (-2 to 2)
        stop: Sequences where the API will stop generating further tokens
        conversation_history: Previous conversation messages
    
    Returns:
        Dictionary with completion information
    """
    try:
        client = _get_openai_client()
        
        # Prepare messages
        messages = []
        
        # Add system message if provided
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)
        
        # Add the current user prompt
        messages.append({"role": "user", "content": prompt})
        
        # Make the API call
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop
        )
        
        # Extract response text
        assistant_message = response.choices[0].message.content
        
        # Return formatted result
        return {
            "response": assistant_message,
            "completion_id": response.id,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            "raw_response": response.model_dump()
        }
    
    except Exception as e:
        print(f"Error in OpenAI chat completion: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }