"""Log of router mistakes the user corrected with /fix, to guide keyword tuning."""
import json
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "router_corrections.jsonl"


def log_correction(message: str, routed: str, corrected: str, path: Path | None = None) -> None:
    path = path or LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "message": message,
        "routed": routed,
        "corrected": corrected,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_corrections(path: Path | None = None) -> list[dict]:
    path = path or LOG_PATH
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
