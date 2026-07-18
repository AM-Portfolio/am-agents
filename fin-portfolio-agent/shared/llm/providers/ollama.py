import os
import json
import logging
import httpx
from typing import List, Dict, Any, Optional
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class OllamaLLMProvider(BaseLLMProvider):
    """
    Ollama LLM provider implementation.
    Connects to local Ollama instance using OpenAI-compatible API.
    """
    
    def __init__(self, model: str = None, base_url: str = None):
        if not model:
            model = os.getenv("LLM_MODEL", "gpt-oss:20b-cloud")
        if not base_url:
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            
        self.model_name = model
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
            
    def is_available(self) -> bool:
        # We assume Ollama is available if configured
        return True
        
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Any:
        payload = {
            "model": self.model_name,
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
            logger.info(f"Sending request to Ollama model: {self.model_name}")
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            choice = data["choices"][0]
            message = choice["message"]
            
            if message.get("tool_calls"):
                return {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": message["tool_calls"]
                }
            
            return message.get("content") or ""
            
        except Exception as e:
            logger.error(f"Ollama API Error with {self.model_name}: {e}")
            return f"Error calling Ollama ({self.model_name}): {str(e)}"
