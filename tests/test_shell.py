import pytest

from shorts.shell import CommandError, run_cmd


def test_run_cmd_success():
    proc = run_cmd(["printf", "hello"])
    assert proc.stdout == "hello"
    assert proc.returncode == 0


def test_run_cmd_raises_on_failure():
    with pytest.raises(CommandError) as excinfo:
        run_cmd(["sh", "-c", "echo boom 1>&2; exit 3"])
    assert excinfo.value.returncode == 3
    assert "boom" in excinfo.value.stderr


def test_run_cmd_stringifies_args(tmp_path):
    target = tmp_path / "x"
    target.write_text("data")
    proc = run_cmd(["cat", target])  # Path, not str
    assert proc.stdout == "data"


def test_run_cmd_respects_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("here")
    proc = run_cmd(["ls"], cwd=tmp_path)
    assert "marker.txt" in proc.stdout
