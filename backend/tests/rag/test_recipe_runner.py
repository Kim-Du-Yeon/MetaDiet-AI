from subprocess import CompletedProcess


def test_native_failure_is_not_success_even_with_zero_exit_code(monkeypatch, tmp_path):
    from scripts.eval import compare_rag_recipes as runner
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: CompletedProcess(
        args=[], returncode=0, stdout="an artifact path\n", stderr="Windows fatal exception: access violation"))
    result = runner.parse_worker({"path": "synthetic.pdf"}, "docling", [1], tmp_path, 5)
    assert result["status"] == "failed"
    assert result["failure_type"] == "native_exception"
