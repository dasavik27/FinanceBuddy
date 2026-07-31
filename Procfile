release: cd backend && python -m migrations.migrate
web: cd backend && python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
