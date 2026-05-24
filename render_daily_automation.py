"""
Daily Islamic content automation.

Each run regenerates the day's content bundle (hadith, ayah, dua, hijri date,
prayer times for major cities) and commits it. Output is real, useful data
the frontend and any consumer can serve — no random padding, no heartbeat
noise. If the source pools or service logic change, this script picks that
up automatically.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

# Make 'app' importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.daily_content import DailyContentService  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent
DAILY_DIR = REPO_ROOT / "data" / "daily"
TODAY_FILE = DAILY_DIR / "today.json"
HISTORY_FILE = DAILY_DIR / "history.json"


def write_today_bundle(service: DailyContentService) -> dict:
    bundle = service.get_today_bundle()
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    with open(TODAY_FILE, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    return bundle


def append_history(bundle: dict) -> None:
    entry = {
        "gregorian_date": bundle["gregorian_date"],
        "hijri": bundle["hijri_date"]["formatted"],
        "hadith_id": bundle["hadith"]["id"],
        "ayah_ref": f"{bundle['ayah']['surah_name_en']}:{bundle['ayah']['ayah_number']}",
        "dua_id": bundle["dua"]["id"],
        "generated_at": bundle["generated_at"],
    }
    history = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    # Replace today's entry if regenerating, otherwise append. Keep most recent 365.
    history = [h for h in history if h.get("gregorian_date") != entry["gregorian_date"]]
    history.append(entry)
    history = history[-365:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def run_git(*args: str) -> int:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=False).returncode


def commit_and_push() -> None:
    if run_git("add", "data/daily/today.json", "data/daily/history.json") != 0:
        return
    status = subprocess.run(
        ["git", "status", "--porcelain", "data/daily/today.json", "data/daily/history.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if not status.stdout.strip():
        print("No content changes — skipping commit")
        return
    today_iso = date.today().isoformat()
    message = f"daily content: {today_iso}"
    if run_git("commit", "-m", message) != 0:
        return
    if os.environ.get("SKIP_PUSH"):
        return
    run_git("push")


def main() -> None:
    service = DailyContentService()
    bundle = write_today_bundle(service)
    append_history(bundle)
    print(f"Generated daily bundle for {bundle['gregorian_date']} ({bundle['hijri_date']['formatted']})")
    print(f"  hadith #{bundle['hadith']['id']} | ayah {bundle['ayah']['surah_name_en']}:{bundle['ayah']['ayah_number']} | dua #{bundle['dua']['id']}")
    commit_and_push()


if __name__ == "__main__":
    main()
