@echo off
cd /d E:\vscode\project\xootour-sanya
python test_store.py > output\_run.log 2>&1
echo EXIT_CODE=%ERRORLEVEL%
type output\_run.log
