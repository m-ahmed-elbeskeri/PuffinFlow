"""OpenAI embeddings integration module for FlowForge."""

import os
import json
from typing import Dict, Any, List, Optional, Union
from openai import OpenAI

# Import to get _get_openai_client function
from integrations.openai.openai import _get_openai_client

def generate_embedding(
    text: str,
    model: str = "text-embedding-3-small"
) -> Dict[str, Any]:
    """
    Generate embeddings for text using OpenAI's embedding models.
    
    Args:
        text: The text to generate embeddings for
        model: The model to use for embeddings
    
    Returns:
        Dictionary with embedding information
    """
    try:
        client = _get_openai_client()
        
        response = client.embeddings.create(
            model=model,
            input=text
        )
        
        embedding = response.data[0].embedding
        
        return {
            "embedding": embedding,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens
            },
            "model": response.model
        }
    
    except Exception as e:
        print(f"Error in OpenAI embedding generation: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }