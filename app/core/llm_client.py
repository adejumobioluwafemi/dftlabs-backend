"""
LLM Client with provider fallback chain.

Priority:
  1. Anthropic Claude (best quality)
  2. NVIDIA NIM — DeepSeek V3.2 (free tier, strong)
  3. NVIDIA NIM — Nemotron Nano 30B (lighter fallback)

Usage:
    from app.core.llm_client import llm_complete

    response = await llm_complete(
        prompt="Write a blog post about...",
        max_tokens=2500,
    )
"""

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
#NVIDIA_PRIMARY_MODEL = "deepseek-ai/deepseek-v3.2"
#NVIDIA_FALLBACK_MODEL = "nvidia/nemotron-3-nano-30b-a3b"
NVIDIA_PRIMARY_MODEL = "meta/llama-3.3-70b-instruct"   
NVIDIA_FALLBACK_MODEL = "mistralai/mistral-7b-instruct-v0.3"  

def _try_anthropic(prompt: str, max_tokens: int) -> str | None:
    """Attempt completion via Anthropic Claude."""
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY.startswith("test"):
        logger.info("[LLM] Anthropic key not configured — skipping")
        return None

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()  # type: ignore
        logger.info("[LLM] Anthropic Claude responded (%d chars)", len(text))
        return text
    except Exception as exc:
        logger.warning("[LLM] Anthropic failed: %s", exc)
        return None


def _try_nvidia(prompt: str, max_tokens: int, model: str) -> str | None:
    """Attempt completion via NVIDIA NIM endpoint (OpenAI-compatible)."""
    #if not settings.NVIDIA_API_KEY or settings.NVIDIA_API_KEY.startswith("your-"): # type: ignore
    #    logger.info("[LLM] NVIDIA key not configured — skipping")
    #    return None
    from app.config import get_settings
    cfg = get_settings()  

    api_key = cfg.NVIDIA_API_KEY
    if not api_key or api_key.startswith("your-"):
        logger.info("[LLM] NVIDIA key not configured — skipping")
        return None
        
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=settings.NVIDIA_API_KEY, # type: ignore
        )

        # Collect streamed response into a single string
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            top_p=0.95,
            max_tokens=max_tokens,
            stream=True,
        )

        chunks: list[str] = []
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            # Skip reasoning tokens (chain-of-thought), only keep content
            content = getattr(delta, "content", None)
            if content:
                chunks.append(content)

        text = "".join(chunks).strip()
        if text:
            logger.info(
                "[LLM] NVIDIA NIM (%s) responded (%d chars)", model, len(text)
            )
            return text

        logger.warning("[LLM] NVIDIA NIM (%s) returned empty response", model)
        return None

    except Exception as exc:
        logger.warning("[LLM] NVIDIA NIM (%s) failed: %s", model, exc)
        return None


def llm_complete(prompt: str, max_tokens: int = 2500) -> str:
    """
    Complete a prompt using the best available LLM provider.

    Fallback chain:
        Anthropic Claude → DeepSeek V3.2 → Nemotron Nano 30B

    Raises:
        RuntimeError: if all providers fail or are unconfigured.
    """
    # 1. Try Anthropic
    result = _try_anthropic(prompt, max_tokens)
    if result:
        return result

    # 2. Try NVIDIA DeepSeek V3.2
    result = _try_nvidia(prompt, max_tokens, NVIDIA_PRIMARY_MODEL)
    if result:
        return result

    # 3. Try NVIDIA Nemotron Nano
    result = _try_nvidia(prompt, max_tokens, NVIDIA_FALLBACK_MODEL)
    if result:
        return result

    raise RuntimeError(
        "All LLM providers failed or are unconfigured. "
        "Set ANTHROPIC_API_KEY or NVIDIA_API_KEY in .env"
    )

async def _try_nvidia_async(prompt: str, max_tokens: int, model: str) -> str | None:
    """Async NVIDIA NIM call — doesn't block the event loop."""
    from app.config import get_settings
    cfg = get_settings()
    api_key = cfg.NVIDIA_API_KEY
    if not api_key or api_key.startswith("your-"):
        logger.info("[LLM] NVIDIA key not configured — skipping")
        return None

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=api_key,
        )
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            top_p=0.95,
            max_tokens=max_tokens,
            stream=True,
            timeout=60,  # fail fast instead of waiting 5 minutes
        )
        chunks: list[str] = []
        async for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            content = getattr(chunk.choices[0].delta, "content", None)
            if content:
                chunks.append(content)

        text = "".join(chunks).strip()
        if text:
            logger.info("[LLM] NVIDIA NIM (%s) responded (%d chars)", model, len(text))
            return text
        logger.warning("[LLM] NVIDIA NIM (%s) returned empty response", model)
        return None

    except Exception as exc:
        logger.warning("[LLM] NVIDIA NIM (%s) failed: %s", model, exc)
        return None


async def llm_complete_async(prompt: str, max_tokens: int = 2500) -> str:
    """Async version of llm_complete for use inside FastAPI/async contexts."""
    result = _try_anthropic(prompt, max_tokens)
    if result:
        return result

    result = await _try_nvidia_async(prompt, max_tokens, NVIDIA_PRIMARY_MODEL)
    if result:
        return result

    result = await _try_nvidia_async(prompt, max_tokens, NVIDIA_FALLBACK_MODEL)
    if result:
        return result

    raise RuntimeError(
        "All LLM providers failed or are unconfigured. "
        "Set ANTHROPIC_API_KEY or NVIDIA_API_KEY in .env"
    )