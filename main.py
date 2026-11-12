"""Main entry point for the NextHire AI backend."""

import uvicorn

from src.shared.utils.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "src.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
