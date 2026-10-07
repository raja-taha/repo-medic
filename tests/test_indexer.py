from pathlib import Path

from repomedic_core.indexer import index_repository, search_symbols


def test_index_sample_python_fixture():
    root = Path(__file__).resolve().parents[1] / "workspaces" / "fixtures" / "sample-python"
    result = index_repository(root, language="python")
    assert result.file_count >= 2
    assert result.symbol_count >= 4
    names = {s["name"] for s in result.symbols}
    assert "divide" in names
    hits = search_symbols(result.symbols, "divide zero")
    assert any(h["name"] == "divide" for h in hits)