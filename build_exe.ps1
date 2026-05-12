# Build LearningDesk.exe with PyInstaller (run from this folder).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --windowed `
  --name "LearningDesk" `
  --collect-all customtkinter `
  main.py

Write-Host "Done. Output: .\dist\LearningDesk\LearningDesk.exe"
