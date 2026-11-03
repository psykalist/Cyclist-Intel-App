@echo off
REM push.bat - double-click wrapper for git-push.sh (the safe push path).
REM git-push.sh stages source only, keeps CI-owned data files out of the commit,
REM clears stale locks, and rebases on origin/main before pushing.
REM Usage: push.bat "vNN: commit message"
cd /d "%~dp0"
set "GITBASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%GITBASH%" (
    echo Git Bash not found at %GITBASH% - install Git for Windows.
    pause
    exit /b 1
)
"%GITBASH%" ./git-push.sh %*
pause
