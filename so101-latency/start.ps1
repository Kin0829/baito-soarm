# Run measure_latency.py in the Windows Miniforge "lerobot" environment.
# Usage: .\start.ps1 --leader-port COM5 --follower-port COM4 --hz 60
$ErrorActionPreference = 'Stop'
$condaRoot = if ($env:SO101_CONDA_ROOT) { $env:SO101_CONDA_ROOT } else { Join-Path $env:USERPROFILE 'miniforge3' }
$envName = if ($env:SO101_CONDA_ENV) { $env:SO101_CONDA_ENV } else { 'lerobot' }
$python = Join-Path $condaRoot "envs\$envName\python.exe"
if (-not (Test-Path $python)) { throw "Python not found at $python. Set SO101_CONDA_ROOT or SO101_CONDA_ENV." }
$envDir = Split-Path $python
$env:PATH = "$envDir;$envDir\Library\bin;$envDir\Scripts;$env:PATH"
Set-Location $PSScriptRoot
& $python measure_latency.py @args
exit $LASTEXITCODE
