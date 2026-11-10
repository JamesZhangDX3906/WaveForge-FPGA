$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $python = if (Test-Path -LiteralPath '.venv/Scripts/python.exe') { '.venv/Scripts/python.exe' } else { 'python' }
    & $python -m PyInstaller --noconfirm --clean --windowed --onedir --name WaveForge-FPGA --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module tkinter --icon resources/icons/waveforge.ico --copy-metadata PySide6-Essentials --copy-metadata shiboken6 main.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    Copy-Item -LiteralPath examples -Destination dist/WaveForge-FPGA -Recurse -Force
    Copy-Item -LiteralPath README.md -Destination dist/WaveForge-FPGA -Force
} finally { Pop-Location }

