@echo off
chcp 65001 >nul
echo ============================================
echo  Apteka - monitor cen
echo ============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Instaluje Python...
    winget install -e --id Python.Python.3 --accept-source-agreements --accept-package-agreements >nul
    for /f "tokens=*" %%p in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"Path\",\"Machine\") + \";\" + [Environment]::GetEnvironmentVariable(\"Path\",\"User\")"') do set "PATH=%%p"
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo BLAD: Uruchom ponownie w nowym oknie cmd.
        pause & exit /b
    )
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo Python: %%i  OK

python -c "import requests" >nul 2>&1 || pip install requests -q
echo Requests: OK
echo.
echo -------- Konfiguracja (zapis do .env, Enter = domyslne/bez zmian) --------
echo.

set "ENVF=%~dp0.env"
set "NEW_NTFY=" & set "NEW_LAT=" & set "NEW_LON="
set /p NEW_NTFY="  Temat ntfy (NTFY_TOPIC): "
echo   Podaj YOUR_LATITUDE_HERE i YOUR_LONGITUDE_HERE jako liczby (np. z map Google)
set /p NEW_LAT="  Szerokosc (GEO_LAT): "
set /p NEW_LON="  Dlugosc   (GEO_LON): "

if not "%NEW_NTFY%%NEW_LAT%%NEW_LON%"=="" (
    > "%ENVF%" echo # Konfiguracja trakmedthc - nie dodawaj do repozytorium
    if not "%NEW_NTFY%"=="" >> "%ENVF%" echo NTFY_TOPIC=%NEW_NTFY%
    if not "%NEW_LAT%"=="" >> "%ENVF%" echo GEO_LAT=%NEW_LAT%
    if not "%NEW_LON%"=="" >> "%ENVF%" echo GEO_LON=%NEW_LON%
    echo Zapisano %ENVF%
) else (
    echo Bez zmian - uzywam istniejacego .env lub wartosci domyslnych.
)

echo.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_PATH=%~dp0apteka_autostart.vbs"
(echo @echo off & echo wscript /nologo "%VBS_PATH%") > "%STARTUP%\apteka_autostart.bat"
echo Autostart: OK

echo.
taskkill /f /im python.exe >nul 2>&1
wscript /nologo "%~dp0apteka_autostart.vbs"
echo Monitor uruchomiony w tle.
echo.
pause
