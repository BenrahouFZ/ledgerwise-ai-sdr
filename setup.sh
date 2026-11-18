#!/usr/bin/env bash
# Mac / Linux: bash setup.sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "Done. Now open .env and paste your API key."
