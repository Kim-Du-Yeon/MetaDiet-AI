"""Opt-in, synthetic-only Gemini capability probe; never prints credentials."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel
from app.core.llm import get_chat_model, response_text


class Echo(BaseModel):
    """Return the given synthetic text."""
    text: str


async def main():
    model = get_chat_model()
    bound = model.bind_tools([Echo], tool_choice="Echo")
    prompt = HumanMessage(content="Call Echo with text equal to synthetic-probe.")
    answer = await bound.ainvoke([prompt])
    assert answer.tool_calls and answer.tool_calls[0]["name"] == "Echo"
    call = answer.tool_calls[0]
    completed = await model.ainvoke([prompt, answer, ToolMessage(content="synthetic-probe", tool_call_id=call["id"])])
    assert response_text(completed)
    print("Native tool call and result continuation: PASS")
    chunks = []
    async for chunk in model.astream("Reply with the word ready."):
        chunks.append(response_text(chunk))
    assert "".join(chunks).strip()
    print("Native streaming: PASS")
    result = await model.with_structured_output(Echo).ainvoke("Return text: ready")
    assert result.text
    print("Structured output: PASS")


if __name__ == "__main__":
    asyncio.run(main())
