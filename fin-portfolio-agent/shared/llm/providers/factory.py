import os
import logging
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)
from .together import TogetherLLMProvider
from .gemini import GeminiLLMProvider
from .ollama import OllamaLLMProvider

def get_llm_provider() -> BaseLLMProvider:
    """Factory to create LLM provider based on env."""
    
    provider_pref = os.getenv("LLM_PROVIDER", "ollama").lower()
    logger.info(f"LLM Provider initialization: {provider_pref}")
    
    if provider_pref == "ollama":
        return OllamaLLMProvider()
        
    # Check for Gemini key in env (Priority)
    google_key = os.getenv("GOOGLE_API_KEY")
    if google_key and provider_pref == "gemini":
        return GeminiLLMProvider(api_key=google_key)
        
    # Check for Together AI key in env
    together_key = os.getenv("TOGETHER_API_KEY")
    if together_key:
        return TogetherLLMProvider(api_key=together_key)
        
    # Fallback
    return TogetherLLMProvider(api_key="") 
