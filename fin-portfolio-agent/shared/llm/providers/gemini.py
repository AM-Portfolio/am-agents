import os
import logging
import asyncio
from google import genai
from google.genai import types
from typing import List, Dict, Any, Optional
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class GeminiLLMProvider(BaseLLMProvider):
    """
    Google Gemini provider implementation.
    Optimized for Gemini 2.5 Flash Lite with robust fallback.
    """
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        # Read from env if not provided
        if not model:
            model = os.getenv("LLM_MODEL", "gemini-2.0-flash-lite")
        # Use short names for the new 'google-genai' SDK
        if model and "models/" in model:
            model = model.split("/")[-1]
        self.model_name = model
        self.client = None # Initialize lazily to avoid loop mismatch
            
    def _get_client(self):
        """Lazy client initialization to ensure it uses the current async loop."""
        if self.client is None:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Gemini Client with model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client: {e}")
        return self.client

    def is_available(self) -> bool:
        return bool(self.api_key)
        
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Any:
        client = self._get_client()
        if not client:
            logger.error("Gemini API key not configured or client initialization failed")
            return "Error: Gemini API key not configured"
            
        system_instruction = None
        contents = []
        
        # Convert messages to SDK format
        for msg in messages:
            role = msg["role"]
            content = msg.get("content") or ""
            
            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=content)]))
            elif role == "assistant":
                parts = []
                if content:
                    parts.append(types.Part(text=content))
                
                # Handle tool calls in assistant history
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        f = tc["function"]
                        parts.append(types.Part(
                            function_call=types.FunctionCall(
                                name=f["name"],
                                args=f.get("arguments") or {}
                            )
                        ))
                
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                # Handle tool results in history
                # Gemini expects role='tool' with function_response parts
                # We try to parse content as JSON if it's a tool output
                try:
                    import json
                    resp_data = json.loads(content)
                except:
                    resp_data = {"output": content}
                    
                contents.append(types.Content(
                    role="tool",
                    parts=[types.Part(
                        function_response=types.FunctionResponse(
                            name=msg.get("name", "unknown"),
                            response=resp_data
                        )
                    )]
                ))
        
        # Configure Tools
        genai_tools = []
        if tools:
            functions = []
            for t in tools:
                if t["type"] == "function":
                    f = t["function"]
                    functions.append(types.FunctionDeclaration(
                        name=f["name"],
                        description=f.get("description", ""),
                        parameters=f.get("parameters")
                    ))
            if functions:
                genai_tools.append(types.Tool(function_declarations=functions))

        # Build Config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
            tools=genai_tools if genai_tools else None
        )

        try:
            logger.info(f"Sending request to Gemini model: {self.model_name}")
            # Use the async client
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            tool_calls = []
            final_text = ""
            
            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.text:
                            final_text += part.text
                        if part.function_call:
                            call = part.function_call
                            tool_calls.append({
                                "id": f"call_{os.urandom(4).hex()}",
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": call.args
                                }
                            })
            
            if tool_calls:
                return {
                    "role": "assistant",
                    "content": final_text,
                    "tool_calls": tool_calls
                }
            
            return final_text or "No response from Gemini."
            
        except Exception as e:
            logger.error(f"Gemini API Error with {self.model_name}: {e}")
            return f"Error calling Gemini ({self.model_name}): {str(e)}"
