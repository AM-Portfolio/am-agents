"""Tests for local image embedder."""
from __future__ import annotations

import base64

import pytest

from app.memory.embedder import cosine_similarity, decode_image_bytes, embed_image


@pytest.mark.asyncio
async def test_embed_same_image_high_similarity():
    # minimal 1x1 png
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    v1 = await embed_image(png_b64)
    v2 = await embed_image(png_b64)
    assert len(v1) == 512
    assert cosine_similarity(v1, v2) > 0.99


@pytest.mark.asyncio
async def test_embed_different_images_lower_similarity():
    png_a = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    png_b = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    v1 = await embed_image(png_a)
    v2 = await embed_image(png_b)
    assert cosine_similarity(v1, v2) < 0.99


def test_decode_strips_data_url_prefix():
    raw = base64.b64encode(b"hello").decode()
    assert decode_image_bytes(f"data:image/png;base64,{raw}") == b"hello"
