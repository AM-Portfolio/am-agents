"""Image embedding for Qdrant ui_patterns similarity search."""
from __future__ import annotations

import base64
import hashlib
import logging
import struct
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

UI_PATTERN_DIM = 512


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(y * y for y in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _fallback_image_vector(image_bytes: bytes, dim: int = UI_PATTERN_DIM) -> List[float]:
    """Deterministic 512-d vector from image bytes — works offline and in unit tests."""
    vec: List[float] = []
    seed = image_bytes
    while len(vec) < dim:
        digest = hashlib.sha256(seed).digest()
        seed = digest
        for i in range(0, len(digest) - 3, 4):
            if len(vec) >= dim:
                break
            vec.append(struct.unpack("!i", digest[i : i + 4])[0] / 2_147_483_648.0)
    mag = sum(x * x for x in vec) ** 0.5
    return [x / mag for x in vec] if mag else vec


def decode_image_bytes(screenshot_base64: str) -> bytes:
    raw = screenshot_base64.strip()
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]
    return base64.b64decode(raw)


async def embed_image_via_litellm(image_bytes: bytes) -> Optional[List[float]]:
    model = (settings.CLIP_EMBEDDING_MODEL or "").strip()
    if not model or not settings.LITELLM_MASTER_KEY:
        return None
    url = f"{settings.LITELLM_BASE_URL.rstrip('/')}/embeddings"
    payload = {
        "model": model,
        "input": base64.b64encode(image_bytes).decode("ascii"),
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {settings.LITELLM_MASTER_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.debug("LiteLLM embeddings failed [%s]: %s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            embedding = data["data"][0]["embedding"]
            if len(embedding) != UI_PATTERN_DIM:
                logger.warning(
                    "Embedding dim=%s expected %s — using fallback",
                    len(embedding),
                    UI_PATTERN_DIM,
                )
                return None
            return [float(x) for x in embedding]
    except Exception as exc:
        logger.debug("LiteLLM embedding error: %s", exc)
        return None


async def embed_image(screenshot_base64: str) -> List[float]:
    image_bytes = decode_image_bytes(screenshot_base64)
    vector = await embed_image_via_litellm(image_bytes)
    if vector is None:
        vector = _fallback_image_vector(image_bytes)
    return vector


async def embed_image_bytes(image_bytes: bytes) -> List[float]:
    vector = await embed_image_via_litellm(image_bytes)
    if vector is None:
        vector = _fallback_image_vector(image_bytes)
    return vector
