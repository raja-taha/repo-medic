from pathlib import Path

from repomedic_core.patching import apply_proposal, validate_proposal
from repomedic_core.schemas import FileEdit, PatchProposal


def test_rejects_path_escape(tmp_path: Path):
    proposal = PatchProposal(
        files=[FileEdit(path="../outside.py", action="create", new_str="x = 1\n")],
        explanation="bad",
    )
    result = validate_proposal(tmp_path, proposal)
    assert not result.ok
    assert any("Unsafe" in e for e in result.errors)


def test_apply_modify_search_replace(tmp_path: Path):
    target = tmp_path / "mod.py"
    target.write_text("x = 1\ny = 2\n", encoding="utf-8")
    proposal = PatchProposal(
        files=[
            FileEdit(path="mod.py", action="modify", old_str="x = 1", new_str="x = 2"),
        ],
        explanation="bump",
    )
    result = apply_proposal(tmp_path, proposal)
    assert result.ok
    assert target.read_text(encoding="utf-8") == "x = 2\ny = 2\n"
    assert "x = 2" in result.unified_diff