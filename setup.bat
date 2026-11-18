@echo off
REM Windows: double click or run setup.bat
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo Done. Now open .env and paste your API key.
