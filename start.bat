@echo off
title Seed Reflection Standalone Product
echo ========================================================
echo Starting Seed Reflection Backend Server on port 8476...
echo ========================================================
set SEED_REFLECTIONS_MODE=local
set SEED_REFLECTIONS_HOST=127.0.0.1
set SEED_REFLECTIONS_PORT=8476
set SEED_REFLECTIONS_DATA_DIR=data
set SEED_REFLECTIONS_UPLOAD_JOBS_DIR=data\uploads\jobs
python server.py
pause
