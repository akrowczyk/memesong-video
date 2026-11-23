import os

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    reload = os.environ.get("RELOAD", "1").lower() in ("1", "true", "yes")
    uvicorn.run("backend.app:app", host=host, port=port, reload=reload)
