# AI Agent Instructions

## Project rules

- Do not rewrite the project from scratch.
- Prefer small, safe changes.
- Keep existing architecture unless explicitly asked.
- Do not edit `.env`.
- Do not commit tokens, logs, databases, or virtual environments.
- Before changing files, explain the plan.
- After changes, list modified files.

## Commands

- Create venv: `python -m venv venv`
- Activate Linux: `source venv/bin/activate`
- Activate Windows: `venv\Scripts\activate`
- Activate PowerShell: `.\venv\Scripts\Activate.ps1`
- Install: `python -m pip install -r requirements.txt`
- Check syntax: `python -m compileall freelance_helper`
- Run: `python -m freelance_helper.app.main`

## Important

- Do not use `git add .`
- Add only specific changed files.
- Keep README consistent with real code in `telegram_bot.py`.
- Use env variable name `FREELANCEHUNT_TOKEN` (not `FREELANCEHUNT_API_TOKEN`).
