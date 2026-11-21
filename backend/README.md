# Tandora Backend

Local-first, AI-powered lead management and personalized outreach application engine.

## Local Development (Windows 11)

### Virtual Environment Setup
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e backend[dev]
```

### Running Tests
```powershell
cd backend
pytest -v
```

### Starting Local Server
```powershell
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
