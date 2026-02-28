from fastapi import FastAPI

from routes_connect import router as connect_router
from routes_main import router as main_router
from routes_settings import router as settings_router
from routes_notifications import router as notif_router
from routes_controller import router as controller_router

app = FastAPI(title="Log Assistant")

# include routers
app.include_router(connect_router)
app.include_router(main_router)
app.include_router(settings_router)
app.include_router(notif_router)
app.include_router(controller_router)

@app.get("/health")
def health():
    return {"status": "ok"}

