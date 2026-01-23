"""Tests for the add_jira_tag.sh script."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).parent.parent / "add_jira_tag.sh"


def _get_git_bash() -> str:
    """Find Git bash executable, prefer it over WSL bash on Windows."""
    if sys.platform != "win32":
        return "bash"

    # Try to find git and derive bash path from it.
    git_path = shutil.which("git")
    if git_path:
        git_dir = Path(git_path).parent
        # git.exe is usually in cmd/ or bin/, bash is in bin/.
        for bash_candidate in [
            git_dir.parent / "bin" / "bash.exe",  # If git is in cmd/.
            git_dir / "bash.exe",  # If git is in bin/.
        ]:
            if bash_candidate.exists():
                return str(bash_candidate)

    # Common Git bash locations as fallback.
    for path in [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ]:
        if Path(path).exists():
            return path

    return "bash"  # Fall back to PATH.


def _run_hook(tmp_path: Path, commit_msg: str, branch_name: str = "fb-PROJ-123-feature") -> tuple[str, str, str, int]:
    """
    Run the hook script with a mocked git branch command.

    Returns (stdout, stderr, result_msg, returncode).
    """
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text(commit_msg)

    wrapper_script = f'''
git() {{
    if [[ "$1" == "branch" && "$2" == "--show-current" ]]; then
        echo "{branch_name}"
        return
    fi
    command git "$@"
}}
export -f git

source "{SCRIPT_PATH.as_posix()}"
'''
    wrapper_file = tmp_path / "wrapper.sh"
    wrapper_file.write_text(wrapper_script)

    result = subprocess.run(
        [_get_git_bash(), wrapper_file.as_posix(), msg_file.as_posix()],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )

    result_msg = msg_file.read_text()
    return result.stdout, result.stderr, result_msg, result.returncode


def test_fresh_commit_adds_tag_to_title(tmp_path: Path) -> None:
    """A fresh commit without any tag gets [TAG] prepended to title."""
    stdout, stderr, result_msg, code = _run_hook(tmp_path, "Add new feature\n")
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == "[PROJ-123] Add new feature\n"
    assert "Adding tag" in stdout


def test_fresh_commit_with_body_adds_tag_to_title(tmp_path: Path) -> None:
    """A fresh commit with body gets [TAG] prepended only to title."""
    input_msg = "Add new feature\n\nThis is the description.\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg)
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == "[PROJ-123] Add new feature\n\nThis is the description.\n"


def test_old_format_converts_to_new(tmp_path: Path) -> None:
    """Old format with tag at end is converted to new format with tag in title."""
    input_msg = "Add new feature\n\nSome description\n\nPROJ-123\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg)
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg.startswith("[PROJ-123] Add new feature")
    assert "PROJ-123\n" not in result_msg.split("\n", 1)[1]  # Not in body.
    assert "Removing old format tag" in stdout


def test_old_format_with_trailing_blank_lines(tmp_path: Path) -> None:
    """Old format with blank lines before tag is cleaned up."""
    input_msg = "Add new feature\n\nDescription\n\n\nPROJ-123\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg)
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg.startswith("[PROJ-123] Add new feature")
    # Should not have multiple trailing newlines.
    assert not result_msg.endswith("\n\n\n")


def test_already_has_bracket_tag_skips(tmp_path: Path) -> None:
    """If tag is already in title with brackets, script skips."""
    input_msg = "[PROJ-123] Add new feature\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg)
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == input_msg  # Unchanged.
    assert "already in title" in stdout


def test_already_has_bracket_tag_with_body_skips(tmp_path: Path) -> None:
    """If tag is already in title, body is preserved and nothing changes."""
    input_msg = "[PROJ-123] Add new feature\n\nDescription here.\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg)
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == input_msg  # Unchanged.


def test_amend_with_branch_in_comments_adds_tag(tmp_path: Path) -> None:
    """Amend scenario: branch name in comments doesn't count as having tag."""
    input_msg = "Add feature\n\n# On branch fb-PROJ-123-feature\n# Changes to be committed:\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg)
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg.startswith("[PROJ-123] Add feature")


def test_non_matching_branch_skips(tmp_path: Path) -> None:
    """Non-matching branch name causes script to skip without changes."""
    input_msg = "Add feature\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg, branch_name="main")
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == input_msg  # Unchanged.
    assert "Skipping" in stdout


def test_release_branch_skips(tmp_path: Path) -> None:
    """Release branch pattern doesn't match, so script skips."""
    input_msg = "Add feature\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg, branch_name="rb-PROJ-v1.0.0")
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == input_msg  # Unchanged.


def test_different_jira_project(tmp_path: Path) -> None:
    """Different JIRA project keys work correctly."""
    input_msg = "Add feature\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg, branch_name="fb-EDEN-2869-some-feature")
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == "[EDEN-2869] Add feature\n"


def test_idempotent_double_run(tmp_path: Path) -> None:
    """Running the script twice produces the same result (idempotent)."""
    input_msg = "Add new feature\n"

    # First run.
    _, stderr1, result1, code1 = _run_hook(tmp_path, input_msg)
    assert code1 == 0, f"Exit code {code1}, stderr: {stderr1}"

    # Second run on result.
    _, stderr2, result2, code2 = _run_hook(tmp_path, result1)
    assert code2 == 0, f"Exit code {code2}, stderr: {stderr2}"
    assert result2 == result1  # Same result.


def test_both_formats_keeps_only_title_tag(tmp_path: Path) -> None:
    """If both new format (title) and old format (bottom) exist, remove the old."""
    input_msg = "[PROJ-123] Add new feature\n\nDescription\n\nPROJ-123\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg)
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == "[PROJ-123] Add new feature\n\nDescription\n"
    # Old format tag should be removed.
    assert "PROJ-123\n" not in result_msg.split("\n", 1)[1]


def test_fixup_commit_not_modified(tmp_path: Path) -> None:
    """Fixup commits should not be modified."""
    input_msg = "fixup! Add new feature\n"
    stdout, stderr, result_msg, code = _run_hook(tmp_path, input_msg)
    assert code == 0, f"Exit code {code}, stderr: {stderr}"
    assert result_msg == input_msg  # Unchanged.
