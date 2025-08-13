@echo off
REM Islamic Q&A Start Script for Windows
REM Quick start script for development and production

echo 🕌 Starting Islamic Q&A Chatbot Backend...

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed or not in PATH
    echo Please install Docker Desktop first
    pause
    exit /b 1
)

REM Check if docker-compose is available
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Compose is not available
    echo Please ensure Docker Compose is installed
    pause
    exit /b 1
)

echo [INFO] Docker is available

REM Create data directories
if not exist "data" mkdir data
if not exist "data\backups" mkdir data\backups
if not exist "data\logs" mkdir data\logs
if not exist "data\cache" mkdir data\cache
if not exist "backups" mkdir backups
if not exist "logs" mkdir logs

echo [INFO] Created data directories

REM Copy environment file if it doesn't exist
if not exist ".env" (
    if exist "config.env" (
        copy "config.env" ".env"
        echo [INFO] Created .env file from config.env
    ) else (
        echo [WARNING] .env file not found. Please create one based on the template.
    )
)

REM Start services
echo [INFO] Starting Docker services...
docker-compose up -d

if %errorlevel% neq 0 (
    echo [ERROR] Failed to start services
    pause
    exit /b 1
)

echo [INFO] Services started successfully!

REM Wait a moment for services to be ready
echo [INFO] Waiting for services to be ready...
timeout /t 10 /nobreak >nul

REM Check if services are running
docker-compose ps

echo.
echo 🎉 Islamic Q&A Backend is now running!
echo.
echo Available services:
echo   API: http://localhost:8000
echo   Documentation: http://localhost:8000/docs
echo   Admin: http://localhost:8000/admin
echo.
echo Useful commands:
echo   View logs: docker-compose logs -f
echo   Stop services: docker-compose down
echo   Restart: docker-compose restart
echo.
echo Press any key to open the API documentation...
pause >nul

REM Try to open documentation in default browser
start http://localhost:8000/docs
