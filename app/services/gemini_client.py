"""Minimal Gemini (Generative Language API) client — text-only, single call.

Scoped to exactly one job: drafting a video script's recording cue ("cola")
from its full body. Anything richer (images, embeddings, multimodal input)
already lives in `labs/integrations/gemini/client.py` for the skills; the api
doesn't need it.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
TEXT_MODEL = "gemini-3.5-flash"
_TIMEOUT_SECONDS = 60.0

_SYSTEM_INSTRUCTION = """\
Você transforma o roteiro falado (texto corrido, de um vídeo gravado de cabeça) na \
COLA de gravação — a cola que fica na tela durante a filmagem, pra guiar sem virar \
teleprompter. Regras de formato, seguidas à risca porque um parser mecânico lê o \
resultado:

- Cada cena/bloco de ideia vira uma seção: uma linha só com **Título Curto** (2-4 \
  palavras, evocativo, não uma frase completa).
- Embaixo do título, bullets ("* ") com o resumo condensado daquela cena — não copie \
  frases inteiras do roteiro, sintetize a ideia.
- Se a cena cita um versículo bíblico entre aspas, um bullet à parte reproduz a \
  citação literal seguida da referência, prefixado por "📖 " — ex: \
  "📖 \\"texto do versículo\\" — Livro 0:0".
- Se a cena menciona o CVV/188, um bullet à parte reproduz a menção, prefixado por \
  "☎️ ".
- Exatamente um bullet por seção — o que funcionaria sozinho numa tela compartilhada \
  — recebe o prefixo "[destaque] " (mantendo o resto do texto do bullet).
- Ao final de cada seção, uma linha sozinha com "[pausa]".
- Sem títulos de nível markdown (#), sem numeração, sem texto fora desse formato. \
  Comece direto na primeira seção — sem H1, sem preâmbulo.
"""


def draft_topics(body: str) -> str:
    """Calls Gemini once with `body` and returns the cola markdown as text.

    Raises HTTPException(502) on any upstream failure — this is a synchronous,
    user-triggered draft, not a background job with its own retry policy.
    """
    if not settings.GEMINI_KEY:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GEMINI_KEY não configurada — geração automática de cola desativada.",
        )

    request_body = {
        "system_instruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": body}]}],
        "generationConfig": {"temperature": 0.4},
    }
    try:
        resp = httpx.post(
            f"{API_BASE}/models/{TEXT_MODEL}:generateContent",
            json=request_body,
            headers={"x-goog-api-key": settings.GEMINI_KEY, "Content-Type": "application/json"},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        res = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Gemini topics draft failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha ao gerar a cola com o Gemini.",
        ) from exc

    candidates = res.get("candidates") or []
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini não retornou candidatos (promptFeedback={res.get('promptFeedback')}).",
        )
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if "text" in p)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini retornou resposta vazia (finishReason={candidates[0].get('finishReason')}).",
        )
    return text.strip()
