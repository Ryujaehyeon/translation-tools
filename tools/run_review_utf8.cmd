@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_review_workflow_utf8.ps1" %*
exit /b %ERRORLEVEL%
