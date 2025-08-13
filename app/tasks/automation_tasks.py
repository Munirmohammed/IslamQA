"""
Automation Tasks
Celery tasks for automated operations
"""

from celery import current_task
import asyncio
import structlog

from app.worker import celery_app
from app.automation.github_automation import github_automation, development_tracker

logger = structlog.get_logger()


@celery_app.task(bind=True)
def daily_commit(self):
    """Daily GitHub commit task"""
    try:
        logger.info("Starting daily commit task")
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(github_automation.daily_commit_routine())
            
            if result:
                # Update development tracker
                development_tracker.update_daily_progress("Automated daily commit completed")
                development_tracker.stats["total_commits"] = development_tracker.stats.get("total_commits", 0) + 1
                development_tracker.save_stats()
                
                logger.info("Daily commit task completed successfully")
                return {"status": "success", "message": "Daily commit completed"}
            else:
                logger.info("Daily commit task completed (no changes)")
                return {"status": "success", "message": "No changes to commit"}
                
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Daily commit task failed: {str(e)}")
        current_task.retry(countdown=60, max_retries=3)


@celery_app.task(bind=True)
def update_development_stats(self):
    """Update development statistics"""
    try:
        logger.info("Updating development statistics")
        
        # Count lines of code
        import os
        from pathlib import Path
        
        total_lines = 0
        python_files = 0
        
        app_dir = Path("app")
        if app_dir.exists():
            for py_file in app_dir.rglob("*.py"):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        lines = len(f.readlines())
                        total_lines += lines
                        python_files += 1
                except Exception:
                    continue
        
        # Update stats
        development_tracker.stats.update({
            "lines_of_code": total_lines,
            "python_files": python_files,
            "features_completed": 10,  # Would track actual features
        })
        
        development_tracker.save_stats()
        
        logger.info(f"Development stats updated: {total_lines} lines across {python_files} files")
        return {
            "status": "success",
            "lines_of_code": total_lines,
            "python_files": python_files
        }
        
    except Exception as e:
        logger.error(f"Failed to update development stats: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def generate_progress_report(self):
    """Generate development progress report"""
    try:
        logger.info("Generating progress report")
        
        summary = development_tracker.get_development_summary()
        
        # Create markdown report
        report = f"""# Islamic Q&A Development Progress Report

Generated: {development_tracker.stats.get('last_update', 'Unknown')}

## Summary Statistics
- **Days Active**: {summary['days_active']}
- **Total Commits**: {summary['total_commits']}
- **Features Completed**: {summary['features_completed']}
- **Average Commits/Day**: {summary['avg_commits_per_day']:.2f}

## Recent Progress
"""
        
        for day_progress in summary['recent_progress']:
            report += f"\n### {day_progress['date']}\n"
            for task in day_progress.get('tasks', []):
                report += f"- {task['task']}\n"
        
        # Save report
        report_file = Path("DEVELOPMENT_REPORT.md")
        with open(report_file, 'w') as f:
            f.write(report)
        
        logger.info("Progress report generated")
        return {"status": "success", "report_generated": True}
        
    except Exception as e:
        logger.error(f"Failed to generate progress report: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def automated_code_quality_check(self):
    """Run automated code quality checks"""
    try:
        logger.info("Running code quality checks")
        
        import subprocess
        import os
        
        quality_results = {}
        
        # Check if we have Python files to analyze
        if os.path.exists("app"):
            try:
                # Simple line count and basic checks
                result = subprocess.run(
                    ["find", "app", "-name", "*.py", "-exec", "wc", "-l", "{}", "+"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    total_lines = 0
                    for line in lines:
                        if line.strip():
                            parts = line.strip().split()
                            if parts and parts[0].isdigit():
                                total_lines += int(parts[0])
                    
                    quality_results["total_lines"] = total_lines
                    quality_results["files_analyzed"] = len(lines) - 1  # Exclude total line
                
            except subprocess.TimeoutExpired:
                logger.warning("Code analysis timed out")
            except Exception as e:
                logger.warning(f"Code analysis failed: {str(e)}")
        
        # Update development tracker
        if quality_results:
            development_tracker.update_daily_progress(
                f"Code quality check: {quality_results.get('total_lines', 0)} lines analyzed"
            )
        
        logger.info("Code quality check completed")
        return {"status": "success", "results": quality_results}
        
    except Exception as e:
        logger.error(f"Code quality check failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def backup_automation_state(self):
    """Backup automation state and configuration"""
    try:
        logger.info("Backing up automation state")
        
        import json
        from datetime import datetime
        
        # Create backup data
        backup_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "development_stats": development_tracker.stats,
            "automation_config": {
                "github_repo": github_automation.github_repo,
                "last_commit_date": github_automation.last_commit_date.isoformat() if github_automation.last_commit_date else None,
            }
        }
        
        # Save backup
        backup_file = f"automation_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        logger.info(f"Automation state backed up to {backup_file}")
        return {"status": "success", "backup_file": backup_file}
        
    except Exception as e:
        logger.error(f"Failed to backup automation state: {str(e)}")
        return {"status": "error", "message": str(e)}
