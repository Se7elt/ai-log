from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/controller", response_class=HTMLResponse)
def controller_settings(request: Request):
    """
    Template page for configuring which log fields to send to the ESP32 controller.
    Currently a placeholder template without backend saving.
    """
    return templates.TemplateResponse("controller.html", {"request": request})

