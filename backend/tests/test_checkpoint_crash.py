import json
import subprocess
import sys
from pathlib import Path


def test_crash_recovery_preserves_pending_tool_and_requires_resume():
    script = Path(__file__).parent / "exception" / "reproduce_checkpoint_crash.py"
    process = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=90
    )
    assert process.returncode == 0, process.stderr
    result_path = process.stdout.split("Results: ")[-1].strip()
    summary = json.loads(Path(result_path).read_text())
    assert summary["crash"]["exit_code"] == -9
    new_input = summary["cases"]["new_human"]
    resume = summary["cases"]["resume_none"]
    assert new_input["checkpoint_id"] == resume["checkpoint_id"]
    assert new_input["response_statuses"] == [400]
    assert new_input["tool_attempts_after_restart"] == 0
    assert new_input["request_roles"] == [["user", "assistant", "user"]]
    assert new_input["after_roles"] == ["human", "ai", "human"]
    assert resume["response_statuses"] == [200]
    assert resume["tool_attempts_after_restart"] == 1
    assert resume["request_roles"] == [["user", "assistant", "tool"]]
    assert resume["after_roles"] == ["human", "ai", "tool", "ai"]
