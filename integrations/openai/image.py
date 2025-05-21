"""OpenAI image generation integration module for FlowForge."""

import os
import json
from typing import Dict, Any, List, Optional, Union
from openai import OpenAI

# Import to get _get_openai_client function
from integrations.openai.openai import _get_openai_client

def generate_image(
    prompt: str,
    model: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "vivid",
    n: int = 1
) -> Dict[str, Any]:
    """
    Generate an image using DALL-E.
    
    Args:
        prompt: The text prompt to generate an image from
        model: The model to use (e.g., dall-e-3, dall-e-2)
        size: Image size (e.g., 1024x1024, 512x512)
        quality: Quality of the image (standard or hd for DALL-E 3)
        style: Style of the image (vivid or natural for DALL-E 3)
        n: Number of images to generate
    
    Returns:
        Dictionary with image information
    """
    try:
        client = _get_openai_client()
        
        # Build parameters based on model
        params = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n
        }
        
        # DALL-E 3 specific parameters
        if model == "dall-e-3":
            params["quality"] = quality
            params["style"] = style
        
        response = client.images.generate(**params)
        
        if n == 1:
            image_url = response.data[0].url
            revised_prompt = getattr(response.data[0], "revised_prompt", None)
            
            result = {
                "image_url": image_url,
                "image_urls": [image_url]
            }
            
            if revised_prompt:
                result["revised_prompt"] = revised_prompt
                
            return result
        else:
            image_urls = [item.url for item in response.data]
            return {
                "image_url": image_urls[0],
                "image_urls": image_urls
            }
    
    except Exception as e:
        print(f"Error in OpenAI image generation: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }