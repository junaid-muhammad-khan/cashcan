"""Vercel entrypoint: exposes the FastAPI app as `app`.

Locally, keep using `uvicorn app.main:app_factory --factory`.
"""
from app.main import create_app

app = create_app()
