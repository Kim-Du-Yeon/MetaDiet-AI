from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_request_and_health_payloads_are_not_written_to_runtime_logs():
    sources = {
        "api": (ROOT / "app/api/routes/main.py").read_text(encoding="utf-8"),
        "confirm": (ROOT / "app/agents/confirm/node.py").read_text(encoding="utf-8"),
        "supervisor": (ROOT / "app/agents/supervisor/node.py").read_text(encoding="utf-8"),
    }
    forbidden = {
        "api": ["raw={inbody_data}", "message='{req.message}'", "response='{str(after_sv", "message='{cv.get("],
        "confirm": ["message='{message}'"],
        "supervisor": ["message='{state.get('message'"],
    }
    for name, fragments in forbidden.items():
        for fragment in fragments:
            assert fragment not in sources[name], f"raw private data logging remains in {name}: {fragment}"


def test_runtime_route_errors_log_categories_not_exception_payloads():
    source = (ROOT / "app/api/routes/main.py").read_text(encoding="utf-8")
    assert "[chat] 오류: {e}" not in source
    assert "[resume] 오류: {e}" not in source


def test_langsmith_production_defaults_hide_payloads_and_trace_ids_are_pseudonymous():
    from app.api.routes.main import _trace_thread_id

    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'LANGSMITH_HIDE_INPUTS", "true"' in main_source
    assert 'LANGSMITH_HIDE_OUTPUTS", "true"' in main_source
    trace_id = _trace_thread_id("550e8400-e29b-41d4-a716-446655440000", "thread-a")
    assert trace_id.startswith("thread-")
    assert "550e8400" not in trace_id
    assert trace_id == _trace_thread_id("550e8400-e29b-41d4-a716-446655440000", "thread-a")
