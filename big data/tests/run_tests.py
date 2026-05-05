import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".pytest_cache" / "v" / "cache" / "lastfailed"


def main():
    cmd = [sys.executable, "-m", "pytest", "-q"]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        print("All tests passed.")
        return 0

    if CACHE.exists():
        try:
            data = json.loads(CACHE.read_text(encoding="utf-8"))
            failed = sorted([k for k, v in data.items() if v])
        except Exception:
            failed = []
    else:
        failed = []

    if failed:
        print("Failed tests:")
        for name in failed:
            print(f"- {name}")
    else:
        print("Tests failed, but no cached list of failed tests was found.")

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
