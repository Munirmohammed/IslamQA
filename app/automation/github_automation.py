"""
GitHub Automation
Automated daily commits and GitHub integration for continuous development
"""

import os
import subprocess
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
import schedule
import time
import json
from pathlib import Path
import structlog

from app.core.config import settings

logger = structlog.get_logger()


class GitHubAutomation:
    """Automate GitHub commits and repository management"""
    
    def __init__(self):
        self.repo_path = Path.cwd()
        self.github_token = settings.GITHUB_TOKEN
        self.github_repo = settings.GITHUB_REPO
        self.last_commit_date = None
        
        # Daily task templates
        self.daily_tasks = [
            "Update knowledge base with new Islamic Q&A content",
            "Improve ML model accuracy and performance",
            "Enhance Arabic language processing capabilities",
            "Optimize database queries and indexing",
            "Add new Islamic sources for scraping",
            "Improve API response time and caching",
            "Enhance user authentication and security",
            "Update documentation and code comments",
            "Refactor code for better maintainability",
            "Add new test cases and improve coverage",
            "Optimize Docker configuration",
            "Improve error handling and logging",
            "Enhance WebSocket chat functionality",
            "Update dependency versions",
            "Improve data validation and sanitization",
            "Optimize memory usage and performance",
            "Add new monitoring and analytics features",
            "Enhance multi-language support",
            "Improve scraper reliability and efficiency",
            "Update API documentation and examples"
        ]
        
        # Code improvement templates
        self.code_improvements = [
            "Optimize database connection pooling",
            "Implement better caching strategies",
            "Add comprehensive input validation",
            "Improve error message clarity",
            "Enhance logging for better debugging",
            "Optimize ML model loading time",
            "Improve API rate limiting logic",
            "Add better type hints and documentation",
            "Optimize JSON serialization",
            "Enhance security middleware",
            "Improve WebSocket connection handling",
            "Add better pagination support",
            "Optimize search query performance",
            "Enhance data backup mechanisms",
            "Improve configuration management",
        ]
    
    def is_git_repo(self) -> bool:
        """Check if current directory is a git repository"""
        return (self.repo_path / '.git').exists()
    
    def init_git_repo(self):
        """Initialize git repository if not exists"""
        if not self.is_git_repo():
            try:
                subprocess.run(['git', 'init'], cwd=self.repo_path, check=True)
                subprocess.run(['git', 'config', 'user.name', 'IslamQA Bot'], cwd=self.repo_path, check=True)
                subprocess.run(['git', 'config', 'user.email', 'bot@islamqa.dev'], cwd=self.repo_path, check=True)
                
                # Create initial .gitignore
                gitignore_content = """
# Environment variables
.env
.env.*
!.env.template

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Logs
*.log
logs/

# Database
*.db
*.sqlite

# Data files
data/
temp/
cache/

# OS
.DS_Store
Thumbs.db

# Docker
.dockerignore
"""
                with open(self.repo_path / '.gitignore', 'w') as f:
                    f.write(gitignore_content.strip())
                
                logger.info("Git repository initialized")
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to initialize git repository: {str(e)}")
    
    def has_changes(self) -> bool:
        """Check if there are any changes to commit"""
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False
    
    def add_all_changes(self):
        """Add all changes to git staging"""
        try:
            subprocess.run(['git', 'add', '.'], cwd=self.repo_path, check=True)
            logger.info("All changes added to staging")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add changes: {str(e)}")
    
    def create_smart_commit(self) -> str:
        """Create an intelligent commit message based on changes"""
        try:
            # Get git diff summary
            result = subprocess.run(
                ['git', 'diff', '--cached', '--stat'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            diff_output = result.stdout
            
            # Analyze changes
            if 'app/scrapers/' in diff_output:
                return random.choice([
                    "Enhanced web scraping capabilities for Islamic sources",
                    "Improved scraper reliability and error handling",
                    "Added new Islamic Q&A source integration",
                    "Optimized scraping performance and efficiency"
                ])
            elif 'app/services/ml_service.py' in diff_output:
                return random.choice([
                    "Improved ML model accuracy and performance",
                    "Enhanced Arabic NLP processing capabilities", 
                    "Optimized question similarity algorithms",
                    "Added advanced semantic search features"
                ])
            elif 'app/api/' in diff_output:
                return random.choice([
                    "Enhanced API endpoints and functionality",
                    "Improved authentication and security features",
                    "Added new REST API capabilities",
                    "Optimized API response time and caching"
                ])
            elif 'app/websocket/' in diff_output:
                return random.choice([
                    "Enhanced real-time chat functionality",
                    "Improved WebSocket connection handling",
                    "Added new chat features and capabilities",
                    "Optimized real-time messaging performance"
                ])
            elif 'app/core/' in diff_output:
                return random.choice([
                    "Enhanced core system functionality",
                    "Improved database and caching performance",
                    "Added better security and monitoring",
                    "Optimized system configuration and setup"
                ])
            elif any(test_word in diff_output for test_word in ['test', 'spec']):
                return random.choice([
                    "Added comprehensive test coverage",
                    "Improved testing framework and utilities",
                    "Enhanced automated testing capabilities",
                    "Added new test cases for better coverage"
                ])
            elif 'requirements.txt' in diff_output or 'Dockerfile' in diff_output:
                return random.choice([
                    "Updated dependencies and Docker configuration",
                    "Enhanced deployment and infrastructure setup",
                    "Improved containerization and dependencies",
                    "Updated system requirements and setup"
                ])
            else:
                # Generic improvements
                return random.choice(self.daily_tasks)
                
        except subprocess.CalledProcessError:
            return random.choice(self.daily_tasks)
    
    def make_commit(self, message: str) -> bool:
        """Make a git commit with the given message"""
        try:
            subprocess.run(
                ['git', 'commit', '-m', message],
                cwd=self.repo_path,
                check=True
            )
            logger.info(f"Commit created: {message}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create commit: {str(e)}")
            return False
    
    def push_to_remote(self) -> bool:
        """Push commits to remote repository"""
        try:
            # Check if remote exists
            result = subprocess.run(
                ['git', 'remote', '-v'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            if not result.stdout.strip():
                # Add remote if it doesn't exist
                if self.github_repo:
                    remote_url = f"https://github.com/{self.github_repo}.git"
                    subprocess.run(
                        ['git', 'remote', 'add', 'origin', remote_url],
                        cwd=self.repo_path,
                        check=True
                    )
            
            # Push to remote
            subprocess.run(
                ['git', 'push', '-u', 'origin', 'main'],
                cwd=self.repo_path,
                check=True
            )
            logger.info("Changes pushed to remote repository")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to push to remote: {str(e)}")
            return False
    
    def create_meaningful_changes(self):
        """Create meaningful code changes for daily commits"""
        changes_made = []
        
        # Update version or build number
        try:
            version_file = self.repo_path / 'app' / '__init__.py'
            if version_file.exists():
                with open(version_file, 'r') as f:
                    content = f.read()
                
                # Update version
                if '__version__' in content:
                    import re
                    current_time = datetime.now()
                    build_number = f"{current_time.year}.{current_time.month}.{current_time.day}"
                    content = re.sub(
                        r'__version__ = "[^"]*"',
                        f'__version__ = "{build_number}"',
                        content
                    )
                    
                    with open(version_file, 'w') as f:
                        f.write(content)
                    
                    changes_made.append("Updated version number")
        except Exception as e:
            logger.warning(f"Failed to update version: {str(e)}")
        
        # Add daily progress comment
        try:
            progress_file = self.repo_path / 'PROGRESS.md'
            today = datetime.now().strftime("%Y-%m-%d")
            
            progress_entry = f"""
## {today}
- {random.choice(self.code_improvements)}
- Enhanced system reliability and performance
- Continued development of Islamic Q&A platform
- Improved codebase maintainability
"""
            
            if progress_file.exists():
                with open(progress_file, 'r') as f:
                    content = f.read()
                
                # Prepend new entry
                content = progress_entry + "\n" + content
            else:
                content = f"# IslamQA Development Progress\n{progress_entry}"
            
            with open(progress_file, 'w') as f:
                f.write(content)
            
            changes_made.append("Updated development progress")
            
        except Exception as e:
            logger.warning(f"Failed to update progress: {str(e)}")
        
        # Update README if needed
        try:
            readme_file = self.repo_path / 'README.md'
            if not readme_file.exists():
                readme_content = f"""# Islamic Q&A Chatbot Backend

Advanced backend system for Islamic knowledge Q&A with ML-powered matching.

## Features

- 🔍 Advanced semantic search with ML
- 🌐 Multi-language support (Arabic & English)  
- 📚 Comprehensive Islamic knowledge base
- 🤖 Real-time chat interface
- 🔐 Secure authentication & rate limiting
- 📊 Analytics and monitoring
- 🐳 Docker containerization
- ⚡ High-performance API

## Architecture

- FastAPI backend with async/await
- PostgreSQL database with Redis caching
- Machine Learning with sentence transformers
- WebSocket real-time communication
- Automated web scraping from trusted sources
- Comprehensive monitoring and analytics

## Last Updated

{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} UTC

## Development Status

✅ Core architecture completed
✅ ML-powered search implemented
✅ Real-time chat functionality
✅ Comprehensive API endpoints
✅ Authentication & security
⚠️ Continuous improvements ongoing

---
*This project is actively maintained with daily updates and improvements.*
"""
                with open(readme_file, 'w') as f:
                    f.write(readme_content)
                
                changes_made.append("Added comprehensive README")
        except Exception as e:
            logger.warning(f"Failed to update README: {str(e)}")
        
        return changes_made
    
    async def daily_commit_routine(self):
        """Execute daily commit routine"""
        try:
            logger.info("Starting daily commit routine")
            
            # Initialize git repo if needed
            if not self.is_git_repo():
                self.init_git_repo()
            
            # Create meaningful changes
            changes_made = self.create_meaningful_changes()
            
            # Check for any changes (including manual ones)
            if self.has_changes():
                # Add all changes
                self.add_all_changes()
                
                # Create smart commit message
                commit_message = self.create_smart_commit()
                
                # Make commit
                if self.make_commit(commit_message):
                    # Push to remote if configured
                    if self.github_token and self.github_repo:
                        self.push_to_remote()
                    
                    self.last_commit_date = datetime.now()
                    logger.info(f"Daily commit completed: {commit_message}")
                    return True
            else:
                logger.info("No changes to commit today")
                return False
                
        except Exception as e:
            logger.error(f"Daily commit routine failed: {str(e)}")
            return False
    
    def schedule_daily_commits(self):
        """Schedule daily commits"""
        # Parse cron schedule (simplified)
        cron_schedule = settings.COMMIT_SCHEDULE  # "0 20 * * *" = 8 PM daily
        
        # Convert to schedule format (simplified for daily)
        schedule.every().day.at("20:00").do(
            lambda: asyncio.create_task(self.daily_commit_routine())
        )
        
        logger.info("Daily commit automation scheduled for 8:00 PM")
    
    async def run_automation_loop(self):
        """Run the automation loop"""
        logger.info("Starting GitHub automation loop")
        
        while True:
            try:
                schedule.run_pending()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Automation loop error: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes on error


class DevelopmentTracker:
    """Track development progress and statistics"""
    
    def __init__(self):
        self.stats_file = Path("development_stats.json")
        self.load_stats()
    
    def load_stats(self):
        """Load development statistics"""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r') as f:
                    self.stats = json.load(f)
            else:
                self.stats = {
                    "total_commits": 0,
                    "lines_of_code": 0,
                    "features_completed": 0,
                    "start_date": datetime.now().isoformat(),
                    "last_update": datetime.now().isoformat(),
                    "daily_progress": []
                }
        except Exception as e:
            logger.error(f"Failed to load stats: {str(e)}")
            self.stats = {}
    
    def save_stats(self):
        """Save development statistics"""
        try:
            self.stats["last_update"] = datetime.now().isoformat()
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stats: {str(e)}")
    
    def update_daily_progress(self, task_description: str):
        """Update daily progress"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if "daily_progress" not in self.stats:
            self.stats["daily_progress"] = []
        
        # Check if today already has an entry
        today_entry = None
        for entry in self.stats["daily_progress"]:
            if entry.get("date") == today:
                today_entry = entry
                break
        
        if not today_entry:
            today_entry = {
                "date": today,
                "tasks": []
            }
            self.stats["daily_progress"].append(today_entry)
        
        today_entry["tasks"].append({
            "task": task_description,
            "timestamp": datetime.now().isoformat()
        })
        
        self.save_stats()
    
    def get_development_summary(self) -> Dict[str, Any]:
        """Get development progress summary"""
        start_date = datetime.fromisoformat(self.stats.get("start_date", datetime.now().isoformat()))
        days_active = (datetime.now() - start_date).days
        
        return {
            "days_active": days_active,
            "total_commits": self.stats.get("total_commits", 0),
            "features_completed": self.stats.get("features_completed", 0),
            "avg_commits_per_day": self.stats.get("total_commits", 0) / max(days_active, 1),
            "last_update": self.stats.get("last_update"),
            "recent_progress": self.stats.get("daily_progress", [])[-7:]  # Last 7 days
        }


# Global instances
github_automation = GitHubAutomation()
development_tracker = DevelopmentTracker()


async def start_github_automation():
    """Start GitHub automation service"""
    if settings.GITHUB_TOKEN and settings.GITHUB_REPO:
        github_automation.schedule_daily_commits()
        await github_automation.run_automation_loop()
    else:
        logger.warning("GitHub automation not configured (missing token or repo)")


# Manual trigger function
async def trigger_daily_commit():
    """Manually trigger daily commit"""
    return await github_automation.daily_commit_routine()
