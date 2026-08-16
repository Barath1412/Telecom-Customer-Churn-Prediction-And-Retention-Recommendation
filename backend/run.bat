@echo off
rem Start the API on Windows (PowerShell or cmd), after checking the three things
rem that actually go wrong.
rem
rem   run.bat                  provider from NARRATION_PROVIDER, default gemini
rem   run.bat fake             force the stub client — no key, no network, no cost
rem   run.bat gemini 8001      provider and port
rem
rem Uses `python -m uvicorn` so the Scripts directory does not need to be on PATH.

setlocal enabledelayedexpansion

rem ---- resolve the repo root relative to THIS file -------------------------
set "HERE=%~dp0"
rem Strip trailing backslash
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
for %%I in ("%HERE%\..") do set "ROOT=%%~fI"

rem ---- arguments -----------------------------------------------------------
set "PROVIDER=%~1"
if "%PROVIDER%"=="" set "PROVIDER=%NARRATION_PROVIDER%"
if "%PROVIDER%"=="" set "PROVIDER=gemini"

set "PORT=%~2"
if "%PORT%"=="" set "PORT=8000"

rem ---- prerequisite checks -------------------------------------------------
if not exist "%ROOT%\ml\src" (
    echo.
    echo   ERROR: no ml\src at %ROOT%\ml — is the ML project in place?
    echo.
    exit /b 1
)

if not exist "%ROOT%\ml\artifacts\churn_model_v1.joblib" (
    echo.
    echo   ERROR: no trained model at ml\artifacts\churn_model_v1.joblib
    echo.
    exit /b 1
)

if not exist "%ROOT%\retention-console-frontend\api-contract" (
    echo.
    echo   ERROR: no api-contract at %ROOT%\retention-console-frontend\api-contract
    echo.
    exit /b 1
)

rem ---- .env warning (gemini only) ------------------------------------------
if /i "%PROVIDER%"=="gemini" (
    if not exist "%ROOT%\ml\.env" (
        echo.
        echo   WARNING: no ml\.env — live narration will fail.
        echo            Copy ml\.env.example to ml\.env and paste your GEMINI_API_KEY.
        echo.
    )
)

rem ---- launch --------------------------------------------------------------
set "NARRATION_PROVIDER=%PROVIDER%"
cd /d "%HERE%"
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
