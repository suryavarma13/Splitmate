# SplitMate Backend Starter Structure

Modular starter structure for SplitMate: Flutter frontend + Django REST Framework backend + MongoDB.

**This ZIP provides folders, configuration starters, placeholder module files, and an expense split calculator. It is not a complete working API.**

## Setup (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py check
```

Before running, add a secure `DJANGO_SECRET_KEY` to `.env`.

## MongoDB note
Django's built-in ORM, migrations, and admin are designed primarily for relational databases. This starter uses a PyMongo repository layout; user authentication and persistence need to be implemented and tested with that approach before production use.
