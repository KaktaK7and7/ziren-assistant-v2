import threading

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.log_bus import add_log, get_logs
from app.events.event_bus import get_events

app = FastAPI(title="Ziren Assistant Local API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://localhost:5173",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/logs")
def logs():
    return {
        "logs": get_logs()
    }


@app.get("/events")
def events():
    return {
        "events": get_events()
    }


def start_local_api() -> None:
    thread = threading.Thread(
        target=lambda: uvicorn.run(
            app,
            host="127.0.0.1",
            port=8787,
            log_level="warning",
        ),
        daemon=True,
    )

    thread.start()

    add_log(
        "Local API запущен",
        meta={
            "url": "http://127.0.0.1:8787/logs",
        },
    )
