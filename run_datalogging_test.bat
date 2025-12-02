@echo off
echo ========================================
echo Iniciando modo datalogging...
echo Logs se guardaran en: datalogging_test.log
echo ========================================
echo.

python -m app.main --datalogging 2>&1 | tee datalogging_test.log
