"""Edits one line per safeguard and runs the tests. Any edit the tests miss is reported."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MUTATIONS = [
    ("app/data.py", 'return [s for s in _load("submissions.json") if s["creator_id"] == creator_id]',
     'return list(_load("submissions.json"))', "creators can open anyone's submission"),
    ("app/sop.py", 'if parsed == "yes" and keyword != "yes":', "if False:",
     "email send no longer needs both consent readings"),
    ("app/sop.py", "if state.failed_verifications >= config.MAX_VERIFY_FAILURES:", "if False:",
     "identity lockout disabled"),
    ("app/verification.py", "verified = len(matched) >= REQUIRED_MATCHES", "verified = len(matched) >= 1",
     "one matching detail is enough to verify"),
    ("app/checks.py", "creator_visible=False))", "creator_visible=True))",
     "originality flag shown to the creator"),
    ("app/data.py", 'return max(pool, key=lambda r: r["agreement_rate"])', "return pool[0]",
     "reviewer routing ignores agreement rate"),
    ("app/state.py", "if message and not pii_value_in_message(k, v, message):", "if False:",
     "model-invented identity details accepted"),
    ("app/sop.py", "user_message = sanitize_control_injection(user_message)", "pass",
     "forged control markers not stripped"),
    ("app/sop.py", "if state.frustration_count >= config.FRUSTRATION_LIMIT:", "if False:",
     "angry creators are never offered a human"),
    ("app/audit.py", "audit_log.setLevel(logging.INFO)", "pass", "audit events not emitted by default"),
    ("app/llm.py", "return ensure_delivery_note(action, ensure_decision(action, reply))",
     "return ensure_decision(action, reply)", "demo-mode email claimed as sent"),
    ("app/llm.py", "system = prompts.generation_system(phase, control)",
     "system = prompts.generation_system(phase)", "turn instructions left out of the system prompt"),
    ("app/llm.py", '    while window and window[0]["role"] != "user":\n        window = window[1:]\n', "",
     "history window can open on an assistant message"),
]


def suite_passes() -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:warnings"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    if not suite_passes():
        print("The suite must pass before mutating anything.")
        return 2
    missed = []
    for rel, old, new, label in MUTATIONS:
        path = ROOT / rel
        original = path.read_text()
        if old not in original:
            print(f"STALE   {label}  (target text not found in {rel})")
            missed.append(label)
            continue
        try:
            path.write_text(original.replace(old, new, 1))
            caught = not suite_passes()
        finally:
            path.write_text(original)
        print(("caught  " if caught else "MISSED  ") + label)
        if not caught:
            missed.append(label)
    print(f"\n{len(MUTATIONS) - len(missed)}/{len(MUTATIONS)} caught")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
