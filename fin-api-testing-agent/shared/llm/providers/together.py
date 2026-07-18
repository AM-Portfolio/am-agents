import os
import aiohttp
import logging
from typing import List, Dict, Any, Optional
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class TogetherLLMProvider(BaseLLMProvider):
    """Together AI provider implementation."""
    
    def __init__(self, api_key: str, model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.together.ai/v1/chat/completions"
        
    def is_available(self) -> bool:
        return bool(self.api_key)
        
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Any:
        if not self.is_available():
            logger.error("Together AI API key not configured")
            return None
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"DEBUG: Together AI API Error: {response.status} - {error_text}")
                        logger.error(f"Together AI API error: {response.status} - {error_text}")
                        return f"Error: API returned {response.status} - {error_text}"
                    
                    data = await response.json()
                    message = data["choices"][0]["message"]
                    
                    # Check for tool_calls
                    if message.get("tool_calls"):
                        return message  # Return the full message object including tool_calls
                    
                    return message.get("content")
                    
        except Exception as e:
            print(f"DEBUG: Exception calling Together AI: {e}")
            logger.error(f"Error calling Together AI: {e}")
            return f"Error: Exception {e}"
