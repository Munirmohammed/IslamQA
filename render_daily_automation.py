"""
Render Daily Automation Script
Runs 5 real update tasks, commits, and pushes to GitHub.
"""
import asyncio
import sys
from app.automation.github_automation import GitHubAutomation
from app.tasks.scraping_tasks import scrape_islamqa, scrape_dar_al_ifta
import subprocess
from app.tasks.ml_tasks import rebuild_faiss_index
from app.tasks.maintenance_tasks import cleanup_old_data
from app.tasks.automation_tasks import update_development_stats
import structlog
import os

logger = structlog.get_logger()

def main():
    from datetime import datetime
    os.makedirs('data', exist_ok=True)

    # Update all automation files before a single commit
    # 1. Heartbeat file
    heartbeat_file = 'data/automation_heartbeat.txt'
    with open(heartbeat_file, 'w', encoding='utf-8') as f:
        f.write(f'Automation heartbeat: {datetime.now().isoformat()}\n')

    # 2. Version bump
    version_file = 'VERSION.txt'
    if os.path.exists(version_file):
        with open(version_file, 'r+') as f:
            try:
                version = int(f.read().strip())
            except Exception:
                version = 0
            version += 1
            f.seek(0)
            f.write(str(version) + '\n')
            f.truncate()
    else:
        with open(version_file, 'w') as f:
            f.write('1\n')

    # 3. Prayer times, random, stats, last_run
    subprocess.run([sys.executable, "scripts/update_prayer_times.py"], check=True)

    # 4. Stage and commit all changes
    github = GitHubAutomation()
    github.add_all_changes()
    github.make_commit("Automated daily update: heartbeat, version, prayer times, stats, random, last_run")
    github.push_to_remote()
    logger.info("Committed and pushed: Automated daily update")

if __name__ == "__main__":
    main()
