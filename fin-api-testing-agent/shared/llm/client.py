from typing import List, Dict, Any, Optional
import logging
from .providers.factory import get_llm_provider

logger = logging.getLogger(__name__)

class LLMClient:
    """Unified LLM Client."""
    
    def __init__(self):
        self.provider = get_llm_provider()
        
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Any:
        """Send chat message to LLM."""
        if not self.provider.is_available():
            logger.warning("LLM provider is not available.")
            return "Error: LLM provider not configured."
            
        return await self.provider.chat_completion(
            messages=messages, 
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice
        )

llm_client = LLMClient()
