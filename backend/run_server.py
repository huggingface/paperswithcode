#!/usr/bin/env python3
"""
Development server runner for the PapersWithCode FastAPI backend.

This script provides an easy way to run the development server with proper
configuration and environment setup.
"""

import uvicorn
from pathlib import Path

from backend.config import get_settings


def main():
    """Run the development server."""
    settings = get_settings()
    project_root = Path(__file__).parent.parent

    print("🚀 Starting PapersWithCode FastAPI Development Server")
    print(f"📊 Database: {settings.database_log_identifier}")
    print(f"🌍 Environment: {settings.environment}")
    print(f"🔧 Host: {settings.host}:{settings.port}")
    print(f"📚 API Docs: http://{settings.host}:{settings.port}/docs")
    print("-" * 50)

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        workers=None if settings.is_development else 2,
        log_level=settings.log_level.lower(),
        access_log=True,
        reload_dirs=[str(project_root / "backend")]
        if settings.is_development
        else None,
    )


if __name__ == "__main__":
    main()
