from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.ocr import vision


async def test_png_uses_correct_mime_and_vision_role(monkeypatch):
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="[]")))
    calls = []
    def factory(**kwargs):
        calls.append(kwargs)
        return model
    monkeypatch.setattr(vision, "get_chat_model", factory)
    assert await vision.read_image(b"\x89PNG\r\n\x1a\nbytes", "foods") == "[]"
    assert calls[0]["role"] == "vision"
    message = model.ainvoke.call_args.args[0][0]
    assert message.content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_non_image_rejected_before_model_call():
    with pytest.raises(ValueError, match="Supported images"):
        await vision.read_image(b"not an image", "parse")
