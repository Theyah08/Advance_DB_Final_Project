@echo off
title Prosfora Gift Shop POS System
color 0D
cls

echo ======================================================================
echo          PROSFORA GIFT SHOP - POINT OF SALE & INVENTORY SYSTEM
echo ======================================================================
echo.
echo [1/3] Checking Python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not found on PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo [2/3] Verifying database and initializing tables...
python init_db.py >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Database initialization check had notices, continuing startup...
) else (
    echo       Database tables and indexes are ready.
)

echo [3/3] Launching Prosfora POS System...
echo.
echo ======================================================================
echo  SYSTEM ONLINE AND READY FOR STORE OPERATIONS!
echo.
echo  * Local Access:     http://127.0.0.1:5000
echo  * Local Network:    Accessible to tablets and laptops on your Wi-Fi
echo.
echo  DEFAULT LOGIN ACCOUNTS:
echo    - Administrator:  Username: admin   ^| Password: admin123
echo    - Cashier:        Username: cashier ^| Password: cashier123
echo.
echo  (Press CTRL+C in this window anytime to stop the system)
echo ======================================================================
echo.

:: Automatically open default browser after a 2-second pause
start "" http://127.0.0.1:5000

:: Start Flask server on all network interfaces
python app.py
pause
