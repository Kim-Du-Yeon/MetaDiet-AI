"""
scripts/visualize_graph.py

컴파일된 LangGraph를 PNG로 렌더링.
xray=True로 meal_planner 서브그래프 내부(meal_plan↔validator)까지 펼쳐서 그림.

실행: venv\\Scripts\\python.exe scripts/visualize_graph.py
출력: scripts/graph.png
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.agents.graph import build_graph

# 체크포인터 없이 구조만 빌드(렌더링 목적)
graph = build_graph()

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph.png")
png = graph.get_graph(xray=True).draw_mermaid_png()   # 서브그래프 펼침
with open(out, "wb") as f:
    f.write(png)
print(f"저장 완료: {out}")
