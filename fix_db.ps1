# fix_db.ps1 - Hard Reset for SOCGUARD Database

Write-Host "--- SOCGUARD HARD RESET INITIATED ---" -ForegroundColor Cyan

# 1. Stop all containers and delete volumes (The "Nucleur Option")
Write-Host "1. Tearing down containers and volumes..." -ForegroundColor Yellow
docker-compose down -v

# 2. Clean up Python cache to ensure no stale bytecode
Write-Host "2. Cleaning up __pycache__..." -ForegroundColor Yellow
Get-ChildItem -Path . -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 3. Rebuild and Start
Write-Host "3. Rebuilding and Starting Containers..." -ForegroundColor Yellow
docker-compose up -d --build

# 4. Wait for Database Health
Write-Host "4. Waiting 15 seconds for PostgreSQL to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# 5. Run Verification
Write-Host "5. Running Verification Script..." -ForegroundColor Yellow
python verify_pipeline.py

Write-Host "--- DONE ---" -ForegroundColor Cyan
