import json
import uuid
import logging
from typing import Dict, Any
from shared.tools.registry import register_tool

logger = logging.getLogger(__name__)

# In-memory store for pending orders (simulate Redis)
PENDING_ORDERS: Dict[str, Dict[str, Any]] = {}

def preview_smart_order(userId: str, symbol: str, action: str = "BUY", quantity: int = 1, orderType: str = "MARKET") -> str:
    """
    [read] Preview a smart order for a stock. Use this when the user asks to buy or sell a stock.
    Returns an ORDER_PREVIEW with a confirmToken. This does NOT place the order.
    You MUST ask the user to confirm the order using the UI widget.
    """
    try:
        confirm_token = str(uuid.uuid4())
        
        order_details = {
            "symbol": symbol.upper(),
            "action": action.upper(),
            "quantity": quantity,
            "type": orderType.upper(),
            "estimatedPrice": 2500.00,
            "totalValue": quantity * 2500.00
        }
        
        PENDING_ORDERS[confirm_token] = order_details
        
        result = {
            "confirmToken": confirm_token,
            "order": order_details,
            "status": "PREVIEW_READY",
            "message": "Order staged. Waiting for user confirmation via UI."
        }
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in preview_smart_order: {e}")
        return json.dumps({"error": str(e)})

# Manually register it
register_tool(
    description="[read] Preview a smart order for a stock. Use this when the user asks to buy or sell a stock. Returns an ORDER_PREVIEW with a confirmToken. This does NOT place the order. You MUST ask the user to confirm the order using the UI widget.",
    parameters={
        "type": "object",
        "properties": {
            "userId": {"type": "string"},
            "symbol": {"type": "string"},
            "action": {"type": "string", "enum": ["BUY", "SELL"]},
            "quantity": {"type": "integer"},
            "orderType": {"type": "string", "enum": ["MARKET", "LIMIT"]}
        },
        "required": ["userId", "symbol"]
    }
)(preview_smart_order)

def place_smart_order(confirmToken: str) -> str:
    """
    [mutate] Execute a previously previewed smart order using its confirmToken.
    Use this ONLY when the user has confirmed the order.
    """
    try:
        if confirmToken not in PENDING_ORDERS:
            return json.dumps({"error": "INVALID_TOKEN", "detail": "The confirmToken is invalid or expired."})
            
        order = PENDING_ORDERS.pop(confirmToken)
        
        result = {
            "status": "EXECUTED",
            "orderId": "ORD-" + str(uuid.uuid4())[:8].upper(),
            "order": order,
            "message": "Order successfully placed on the exchange."
        }
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in place_smart_order: {e}")
        return json.dumps({"error": str(e)})

register_tool(
    description="[mutate] Execute a previously previewed smart order using its confirmToken. Use this ONLY when the user has confirmed the order.",
    parameters={
        "type": "object",
        "properties": {
            "confirmToken": {"type": "string"}
        },
        "required": ["confirmToken"]
    }
)(place_smart_order)

