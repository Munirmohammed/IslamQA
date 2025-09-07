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
    # Ensure data directory exists for all tasks that may write to it
    os.makedirs('data', exist_ok=True)
    github = GitHubAutomation()
    update_tasks = [
        (lambda: scrape_islamqa(5), "Scraped new Q&A from IslamQA.info"),
        (lambda: scrape_dar_al_ifta(5), "Scraped new Q&A from Dar al-Ifta"),
        (lambda: rebuild_faiss_index(True), "Rebuilt FAISS ML index"),
        (lambda: cleanup_old_data(), "Cleaned up old data in DB"),
        (lambda: update_development_stats(), "Updated development stats/analytics"),
        # Prayer times update
        (lambda: subprocess.run([sys.executable, "scripts/update_prayer_times.py"], check=True), "Updated daily prayer times"),
    ]

    for func, msg in update_tasks:
        try:
            logger.info(f"Running: {msg}")
            func()
            github.add_all_changes()
            github.make_commit(msg)
            github.push_to_remote()
            logger.info(f"Committed and pushed: {msg}")
        except Exception as e:
            logger.error(f"Task failed: {msg} | {str(e)}")

if __name__ == "__main__":
    main()
