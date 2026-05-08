@echo off
echo ===================================================
echo Starting SOCGUARD Backend
echo ===================================================

echo Checking if Docker is running...
docker-compose up -d
if %errorlevel% neq 0 (
    echo [ERROR] Docker Compose failed! Make sure Docker Desktop is running.
    echo Attempting to run locally via Python instead...
    
    if exist .venv\Scripts\activate.bat (
        call .venv\Scripts\activate.bat
        pip install -r src\backend-api\requirements.txt
        python src\backend-api\main.py
    ) else (
        echo [ERROR] Python virtual environment not found at .venv. 
        echo Please ensure you run this inside the correct Python environment.
        pause
    )
) else (
    echo [SUCCESS] Docker containers started.
    echo Waiting 5 seconds for backend to initialize...
    timeout /t 5 /nobreak > nul
    echo.
    echo Backend logs:
    docker-compose logs --tail=20 backend-api
    echo.
    echo If you still cannot connect to http://localhost:8000, please share the logs above.
    pause
)
