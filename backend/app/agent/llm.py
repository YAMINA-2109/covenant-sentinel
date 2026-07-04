"""Reliability-first wrapper around Vultr Serverless Inference.

Design decision: we deliberately do NOT depend on native function-calling
support of the served model. Every structured call is prompt-constrained
JSON, validated against a Pydantic model, with corrective retries.
Deterministic math never happens in the model — it happens in app/tools/.
"""

import asyncio
import json
import re
from typing import TypeVar

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, InternalServerError
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> str:
    text = _THINK_BLOCK.sub("", text).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    match = _JSON_BLOCK.search(text)
    if not match:
        raise ValueError("no JSON object found in model output")
    return match.group(0)


class VultrLLM:
    """Streaming-first: the Vultr gateway 504s on long non-streaming
    generations (nginx idle timeout), so every call streams tokens and
    retries transient 5xx/connection errors with backoff."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.vultr_api_key,
            base_url=settings.vultr_base_url,
            timeout=240.0,
            max_retries=0,  # we do our own retry loop around the whole stream
        )
        self.model = settings.vultr_chat_model

    async def chat(self, system: str, user: str, temperature: float = 0.0) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    stream=True,
                    max_tokens=6000,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    # Reasoning mode multiplies latency ~50x on this endpoint
                    # (benchmarked 3.2s vs 4+ min per call) with no quality gain
                    # for schema-constrained extraction/selection tasks.
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
                parts: list[str] = []
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        parts.append(chunk.choices[0].delta.content)
                content = "".join(parts)
                return _THINK_BLOCK.sub("", content).strip()
            except (InternalServerError, APITimeoutError, APIConnectionError) as exc:
                last_error = exc
                await asyncio.sleep(2.0 * (attempt + 1))
        raise RuntimeError(f"Vultr chat failed after 3 attempts: {last_error}")

    async def chat_json(
        self, system: str, user: str, schema: type[T], max_retries: int = 2
    ) -> T:
        """Ask for JSON matching `schema`, validate, retry with the error fed back."""
        schema_hint = json.dumps(schema.model_json_schema())
        base_prompt = (
            f"{user}\n\n"
            "Answer with ONE JSON object only — no prose, no markdown fences. "
            f"It must validate against this JSON Schema:\n{schema_hint}"
        )
        prompt = base_prompt
        last_error = ""
        for _ in range(max_retries + 1):
            raw = await self.chat(system, prompt)
            try:
                return schema.model_validate_json(_extract_json(raw))
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)[:800]
                prompt = (
                    f"{base_prompt}\n\nYour previous answer failed validation:\n"
                    f"{last_error}\nReturn the corrected JSON object only."
                )
        raise RuntimeError(f"LLM failed to produce valid {schema.__name__}: {last_error}")
