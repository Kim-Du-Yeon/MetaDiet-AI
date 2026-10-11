"""Shared Gemini image input; byte signature determines the declared MIME type."""
import base64

from langchain_core.messages import HumanMessage
from app.core.llm import get_chat_model


async def read_image(image_bytes: bytes, prompt: str, *, max_tokens: int = 1024) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif image_bytes.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("Supported images: JPEG, PNG, WebP")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    model = get_chat_model(role="vision", temperature=0, max_tokens=max_tokens)
    response = await model.ainvoke([HumanMessage(content=[
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
    ])])
    return response.content
