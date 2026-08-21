from __future__ import annotations

import os

from dotenv import load_dotenv
from waitress import serve

from .web import app

load_dotenv()


if __name__ == "__main__":
    serve(
        app,
        host=os.getenv("WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("WEB_PORT", "5000")),
        threads=int(os.getenv("WEB_THREADS", "6")),
    )
