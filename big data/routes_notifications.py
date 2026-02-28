from fastapi import APIRouter
from fastapi.responses import JSONResponse
from config import load_notifications, save_notifications
from config import add_notification

router = APIRouter()


@router.get("/notifications")
def get_notifications():
    notifs = load_notifications()
    return JSONResponse(content={"notifications": notifs, "count": len(notifs)})


@router.post("/notifications/clear")
def clear_notifications():
    save_notifications([])
    return JSONResponse(content={"ok": True, "count": 0})


@router.post("/notifications/add")
def add_notifications_endpoint(title: str = None, text: str = None):
    title = title or "Notification"
    text = text or ""
    try:
        add_notification(title, text)
        notifs = load_notifications()
        return JSONResponse(content={"ok": True, "count": len(notifs)})
    except Exception:
        return JSONResponse(content={"ok": False}, status_code=500)

