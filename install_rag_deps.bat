@echo off
chcp 65001 >nul
echo Installing RAG dependencies...
echo.
"%~dp0.venv312\Scripts\python.exe" -m pip install scikit-learn
echo.
echo Done!
pause

