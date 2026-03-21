from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from config import load_settings, save_settings_file, load_filters, save_filters_file, add_notification, load_config, CONFIG_FILE, SETTINGS_FILE
from db import get_logs_conn
from pathlib import Path
from rag import DOCS_DIR, reindex_documents

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    settings = load_settings() or {}
    ai_provider = (settings.get("ai_provider") or "ollama").strip().lower()
    ai_options = settings.get("ai_options") or {}
    rag_enabled = bool(settings.get("rag_enabled"))
    rag_embedding_model = settings.get("rag_embedding_model", "")
    rag_top_k = settings.get("rag_top_k", 4)
    rag_max_chars = settings.get("rag_max_chars", 2000)
    try:
        rag_docs = []
        if DOCS_DIR.exists():
            rag_docs = [p.name for p in DOCS_DIR.iterdir() if p.is_file() and p.suffix.lower() in (".txt", ".md")]
        rag_docs.sort()
    except Exception:
        rag_docs = []

    try:
        from ai import get_available_models, get_providers
        models = get_available_models(provider=ai_provider)
        providers = get_providers()
        try:
            from ai import get_embedding_models
            embedding_models = get_embedding_models(provider="lmstudio")
        except Exception:
            embedding_models = []
    except Exception:
        models = [settings.get("model", "qwen3:4b")]
        providers = [
            {"value": "ollama", "label": "Ollama"},
            {"value": "lmstudio", "label": "LM Studio"},
        ]
        embedding_models = []

    filters = load_filters() or {}
    filters_lines = []
    for name, obj in filters.items():
        words = obj.get("words", []) if isinstance(obj, dict) else []
        color = obj.get("color", "") if isinstance(obj, dict) else ""
        if color:
            filters_lines.append(f"{name}: {color} {' '.join(words)}")
        else:
            filters_lines.append(f"{name}: {' '.join(words)}")

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "models": models,
            "providers": providers,
            "ai_provider": ai_provider,
            "filters_text": "\n".join(filters_lines),
            "ai_options": ai_options,
            "rag_enabled": rag_enabled,
            "rag_embedding_model": rag_embedding_model,
            "rag_top_k": rag_top_k,
            "rag_max_chars": rag_max_chars,
            "rag_docs": rag_docs,
            "embedding_models": embedding_models,
        },
    )


@router.get("/ai_models")
def ai_models(provider: str = "ollama"):
    try:
        from ai import get_available_models
        models = get_available_models(provider=provider)
        return {"models": models}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "models": []})


@router.get("/embedding_models")
def embedding_models():
    try:
        from ai import get_embedding_models
        models = get_embedding_models(provider="lmstudio")
        return {"models": models}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "models": []})


def _to_int(value):
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value):
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    try:
        return float(value.replace(",", "."))
    except Exception:
        return None


@router.post("/settings")
def save_settings(
    logs_per_page: int = Form(...),
    ai_provider: str = Form("ollama"),
    model: str = Form(...),
    context_length: str = Form(""),
    gpu_offload: str = Form(""),
    cpu_threads: str = Form(""),
    eval_batch_size: str = Form(""),
    temperature: str = Form(""),
    rag_enabled: str = Form(""),
    rag_embedding_model: str = Form(""),
    rag_top_k: str = Form(""),
    rag_max_chars: str = Form(""),
):
    settings = load_settings() or {}
    provider = (ai_provider or "ollama").strip().lower()

    settings["logs_per_page"] = logs_per_page
    settings["ai_provider"] = provider
    settings["model"] = model
    ai_options = {}
    ctx = _to_int(context_length)
    gpu = _to_int(gpu_offload)
    cpu = _to_int(cpu_threads)
    batch = _to_int(eval_batch_size)
    temp = _to_float(temperature)
    if ctx is not None:
        ai_options["context_length"] = ctx
    if gpu is not None:
        ai_options["gpu_offload"] = gpu
    if cpu is not None:
        ai_options["cpu_threads"] = cpu
    if batch is not None:
        ai_options["eval_batch_size"] = batch
    if temp is not None:
        ai_options["temperature"] = temp
    settings["ai_options"] = ai_options
    settings["rag_enabled"] = bool(rag_enabled)
    if rag_embedding_model is not None:
        settings["rag_embedding_model"] = rag_embedding_model.strip()
    rag_top_k_int = _to_int(rag_top_k)
    rag_max_chars_int = _to_int(rag_max_chars)
    if rag_top_k_int is not None:
        settings["rag_top_k"] = rag_top_k_int
    if rag_max_chars_int is not None:
        settings["rag_max_chars"] = rag_max_chars_int
    save_settings_file(settings)
    try:
        add_notification(
            "Settings updated",
            f"logs_per_page={logs_per_page}, ai_provider={provider}, model={model}, ai_options={len(ai_options)}",
        )
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
    return _reset_with_options(
        remove_ai_db=True,
        remove_docs=True,
        remove_index=True,
    )


def _reset_with_options(remove_ai_db: bool, remove_docs: bool, remove_index: bool):
    cfg = load_config()
    if cfg and remove_ai_db:
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
    if remove_docs:
        try:
            if DOCS_DIR.exists():
                for p in DOCS_DIR.iterdir():
                    if p.is_file():
                        p.unlink()
        except Exception:
            pass
    if remove_index:
        try:
            from rag import INDEX_FILE
            if INDEX_FILE.exists():
                INDEX_FILE.unlink()
        except Exception:
            pass
    return RedirectResponse("/connect", status_code=303)


@router.post("/reset_custom")
def reset_custom(
    remove_ai_db: str = Form(""),
    remove_docs: str = Form(""),
    remove_index: str = Form(""),
):
    return _reset_with_options(
        remove_ai_db=bool(remove_ai_db),
        remove_docs=bool(remove_docs),
        remove_index=bool(remove_index),
    )


@router.post("/rag/upload")
def rag_upload(file: UploadFile = File(...)):
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    filename = (file.filename or "").strip()
    if not filename:
        return RedirectResponse("/settings", status_code=303)
    suffix = Path(filename).suffix.lower()
    if suffix not in (".txt", ".md"):
        try:
            add_notification("RAG upload skipped", f"Unsupported file type: {suffix}")
        except Exception:
            pass
        return RedirectResponse("/settings", status_code=303)
    dest = DOCS_DIR / Path(filename).name
    with dest.open("wb") as f:
        f.write(file.file.read())
    try:
        add_notification("RAG document uploaded", dest.name)
    except Exception:
        pass
    return RedirectResponse("/settings", status_code=303)


@router.post("/rag/reindex")
def rag_reindex():
    settings = load_settings() or {}
    embed_model = settings.get("rag_embedding_model", "")
    if not embed_model:
        try:
            add_notification("RAG reindex skipped", "Embedding model is not configured")
        except Exception:
            pass
        return RedirectResponse("/settings", status_code=303)
    try:
        count = reindex_documents(embed_model)
        add_notification("RAG index updated", f"chunks={count}")
    except Exception as e:
        try:
            add_notification("RAG reindex error", str(e))
        except Exception:
            pass
    return RedirectResponse("/settings", status_code=303)


@router.post("/rag/delete")
def rag_delete(filename: str = Form(...)):
    name = (filename or "").strip()
    if not name:
        return RedirectResponse("/settings", status_code=303)
    path = DOCS_DIR / name
    try:
        if path.exists() and path.is_file():
            path.unlink()
            try:
                add_notification("RAG document deleted", name)
            except Exception:
                pass
    except Exception as e:
        try:
            add_notification("RAG delete error", str(e))
        except Exception:
            pass
    return RedirectResponse("/settings", status_code=303)


@router.post("/rag/clear_index")
def rag_clear_index():
    try:
        from rag import INDEX_FILE
        if INDEX_FILE.exists():
            INDEX_FILE.unlink()
            try:
                add_notification("RAG index cleared", "Index file removed")
            except Exception:
                pass
    except Exception as e:
        try:
            add_notification("RAG clear index error", str(e))
        except Exception:
            pass
    return RedirectResponse("/settings", status_code=303)
