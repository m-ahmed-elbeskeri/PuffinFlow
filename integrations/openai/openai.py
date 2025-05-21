"""OpenAI integration for FlowForge with support for completions, chat, and embeddings."""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional, Union
import openai
from openai import OpenAI

# Async client
client = None

def _get_openai_client():
    """Get or create OpenAI client."""
    global client
    
    if not client:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required. Please set it with your OpenAI API key.")
        
        client = OpenAI(api_key=api_key)
    
    return client

def text_completion(
    prompt: str,
    model: str = "gpt-3.5-turbo-instruct",
    temperature: float = 0.7,
    max_tokens: int = 256,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    stop: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Generate a text completion using OpenAI's legacy completions endpoint.
    
    Args:
        prompt: The prompt to send to the model
        model: The model to use for the completion
        temperature: Temperature for sampling (0-2)
        max_tokens: Maximum number of tokens to generate
        top_p: Top-p sampling value (0-1)
        frequency_penalty: Frequency penalty (-2 to 2)
        presence_penalty: Presence penalty (-2 to 2)
        stop: Sequences where the API will stop generating further tokens
    
    Returns:
        Dictionary with completion information
    """
    try:
        client = _get_openai_client()
        
        response = client.completions.create(
            model=model,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop
        )
        
        return {
            "text": response.choices[0].text,
            "completion_id": response.id,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
    
    except Exception as e:
        print(f"Error in OpenAI text completion: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }