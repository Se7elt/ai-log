import json
from pathlib import Path
from datetime import datetime

CONFIG_FILE = Path("config.json")
SETTINGS_FILE = Path("settings.json")
FILTERS_FILE = Path("filters.json")
NOTIF_FILE = Path("notifications.json")

LOGS_PER_PAGE = 10

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return None

def save_config(data: dict):
    CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_settings():
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    return {}

def save_settings_file(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_filters():
    if FILTERS_FILE.exists():
        try:
            raw = json.loads(FILTERS_FILE.read_text(encoding="utf-8"))
            normalized = {}
            default_colors = {
                "error": "#fdecea",
                "warn": "#fff8e1",
                "info": "#e8f5e9",
            }
            for k, v in raw.items():
                name = k.strip().lower()
                if isinstance(v, dict):
                    words = [w.strip().lower() for w in v.get("words", []) if w]
                    color = v.get("color") or default_colors.get(name, "")
                elif isinstance(v, list):
                    words = [w.strip().lower() for w in v if w]
                    color = default_colors.get(name, "")
                else:
                    continue
                if words:
                    normalized[name] = {"words": words, "color": color}
            return normalized
        except Exception:
            return {}
    return {}

def save_filters_file(data: dict):
    FILTERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_notifications():
    if NOTIF_FILE.exists():
        try:
            return json.loads(NOTIF_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_notifications(data: list):
    NOTIF_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def add_notification(title: str, text: str = ""):
    try:
        notifs = load_notifications() or []
        item = {
            "title": title,
            "text": text,
            "time": datetime.now().isoformat(timespec="seconds")
        }
        notifs.insert(0, item)
        notifs = notifs[:200]
        save_notifications(notifs)
    except Exception:
        pass

