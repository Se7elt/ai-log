from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from config import load_settings, save_settings_file, load_filters, save_filters_file, add_notification, load_config, save_config, FILTERS_FILE, SETTINGS_FILE, CONFIG_FILE
from db import get_logs_conn

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    settings = load_settings() or {}
    try:
        from ai import get_available_models
        models = get_available_models()
    except Exception:
        models = [settings.get("model", "qwen3:4b")]
    filters = load_filters() or {}
    filters_lines = []
    for name, obj in filters.items():
        words = obj.get("words", []) if isinstance(obj, dict) else []
        color = obj.get("color", "") if isinstance(obj, dict) else ""
        if color:
            filters_lines.append(f"{name}: {color} {' '.join(words)}")
        else:
            filters_lines.append(f"{name}: {' '.join(words)}")

    return templates.TemplateResponse("settings.html", {"request": request, "settings": settings, "models": models, "filters_text": "\n".join(filters_lines)})


@router.post("/settings")
def save_settings(logs_per_page: int = Form(...), model: str = Form(...)):
    settings = load_settings() or {}
    settings["logs_per_page"] = logs_per_page
    settings["model"] = model
    save_settings_file(settings)
    try:
        add_notification("Settings updated", f"logs_per_page={logs_per_page}, model={model}")
    except Exception:
        pass
    return RedirectResponse("/", status_code=303)


@router.post("/filters")
def save_filters(filters_text: str = Form(...)):
    out = {}
    default_colors = {
        "error": "#fdecea",
        "warn": "#fff8e1",
        "info": "#e8f5e9",
    }
    for raw_line in filters_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line:
            name, rest = line.split(":", 1)
            name = name.strip().lower()
            tokens = [t.strip() for t in rest.strip().split() if t.strip()]
            color = ""
            words = []
            if tokens:
                first = tokens[0]
                if first.startswith("#") and (len(first) in (4, 7)):
                    color = first
                    words = [w.lower() for w in tokens[1:]]
                else:
                    words = [w.lower() for w in tokens]
            if not color:
                color = default_colors.get(name, "")
            if words:
                out[name] = {"words": words, "color": color}
        else:
            continue
    save_filters_file(out)
    try:
        add_notification("Filters updated", f"{len(out)} filters")
    except Exception:
        pass
    return RedirectResponse("/settings", status_code=303)


@router.post("/reset")
def reset_all():
    cfg = load_config()
    if cfg:
        try:
            conn = get_logs_conn(cfg)
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS log_solutions")
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            try:
                add_notification("Reset error", str(e))
            except Exception:
                pass
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
    try:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
    except Exception:
        pass
    try:
        if SETTINGS_FILE.exists():
            SETTINGS_FILE.unlink()
    except Exception:
        pass
    return RedirectResponse("/connect", status_code=303)

