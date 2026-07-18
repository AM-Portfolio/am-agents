import os
import aiohttp
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class LLMClient:
    """Unified LLM Client using the am-agents platform configuration."""
    
    def __init__(self):
        # Resolve config from environment variables
        self.api_key = (
            os.getenv("LITELLM_MASTER_KEY", "").strip() or 
            os.getenv("TOGETHER_API_KEY", "").strip() or 
            os.getenv("LLM_API_KEY", "").strip()
        )
        # Determine Base URL
        base_url = (
            os.getenv("LITELLM_BASE_URL", "").strip() or 
            os.getenv("LLM_BASE_URL", "").strip()
        )
        if not base_url:
            # Fallback to Together AI default
            base_url = "https://api.together.ai/v1"
            
        self.base_url = base_url.rstrip("/") + "/chat/completions"
        
        # Determine Model
        self.model = (
            os.getenv("LLM_MODEL", "").strip() or 
            os.getenv("LLM_PLANNER_MODEL", "").strip() or 
            "meta-llama/Llama-3.3-70B-Instruct-Turbo"
        )
        
    def is_available(self) -> bool:
        return bool(self.api_key)
        
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Any:
        """Send chat message to LLM."""
        if not self.is_available():
            logger.warning("LLM client API key is not configured.")
            return "Error: LLM client API key is not configured."
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1000,
            "stream": False
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
                        logger.error(f"LLM API Error: {response.status} - {error_text}")
                        return f"Error: LLM API returned {response.status} - {error_text}"
                        
                    data = await response.json()
                    message = data["choices"][0]["message"]
                    
                    if message.get("tool_calls"):
                        return message
                        
                    return message.get("content")
                    
        except Exception as e:
            logger.error(f"Exception calling LLM: {e}")
            return f"Error: Exception calling LLM: {e}"

llm_client = LLMClient()
