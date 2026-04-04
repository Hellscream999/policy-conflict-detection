@echo off
REM ============================================
REM Policy Conflict Detection - Run All Proofs
REM ============================================

echo.
echo ========================================
echo POLICY CONFLICT DETECTION PROOF
echo ========================================
echo.

REM Check Python
py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

REM Run proof generation
echo Running proof generation...
echo.
py prove_paper.py

echo.
echo ========================================
echo PROOF GENERATION COMPLETE
echo ========================================
echo.
echo Figures saved to: figures\
echo Results saved to: results\
echo.
echo Opening figures folder...
start figures

pause
