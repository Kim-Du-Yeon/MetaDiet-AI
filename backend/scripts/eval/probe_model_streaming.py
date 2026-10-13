"""Provider-only synthetic streaming probe; not an Agent end-to-end benchmark."""
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT / 'backend/.env')
from app.core.llm import get_chat_model, response_text


async def main():
    rows = []
    model = get_chat_model()
    prompt = '합성 평가입니다. 점심으로 한식뷔페를 이용하는 사람에게 간단한 접시 구성 팁 세 가지를 한국어로 설명하세요. 수치나 건강상태를 추정하지 마세요.'
    for index in range(3):
        start = perf_counter()
        first = None
        chunks = chars = 0
        finish_reason = None
        async for chunk in model.astream(prompt):
            finish_reason = chunk.response_metadata.get('finish_reason', finish_reason)
            text = response_text(chunk)
            if text:
                first = first if first is not None else perf_counter() - start
                chunks += 1
                chars += len(text)
        if first is None:
            raise RuntimeError('No visible text in provider stream')
        rows.append({'repeat': index, 'first_text_ms': round(first * 1000, 1),
                     'total_ms': round((perf_counter()-start)*1000, 1),
                     'visible_chunks': chunks, 'characters': chars, 'finish_reason': finish_reason})
    out = ROOT / 'docs/coaching_stages/MODEL_STREAMING.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'scope': 'provider_only_synthetic_no_tools', 'rows': rows}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(rows))


if __name__ == '__main__':
    asyncio.run(main())
