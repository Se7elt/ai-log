from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from db import get_logs_conn, ensure_solution_table
from config import load_config, load_settings, load_filters, add_notification, LOGS_PER_PAGE
from ai import generate_solution
from psycopg2 import sql
from math import ceil

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    page: int = 1,
    sort: str = "id",
    order: str = "desc",
    level: str = "all",
    q: str = ""
):
    cfg = load_config()
    db_connected = bool(cfg and "table" in cfg)

    if not db_connected:
        # Render placeholders when no DB connection is configured
        columns = ["col1", "col2", "col3"]
        # create 10 placeholder rows with None values
        rows = [(None, None, None) for _ in range(10)]
        page = 1
        total_pages = 1
        total_logs = 0
        filters = load_filters() or {}
        ai_model = (load_settings() or {}).get("model")

        return templates.TemplateResponse("index.html", {
            "request": request,
            "rows": rows,
            "columns": columns,
            "page": page,
            "total_pages": total_pages,
            "total_logs": total_logs,
            "sort": sort,
            "order": order,
            "level": level,
            "q": q,
            "filters_keys": ["all"] + sorted(k.lower() for k in filters.keys()),
            "filters": {k.lower(): v for k, v in filters.items()},
            "ai_model": ai_model,
            "db_connected": False
        })

    try:
        conn = get_logs_conn(cfg)
        cur = conn.cursor()
        cur.execute(sql.SQL("SELECT * FROM {} LIMIT 0").format(sql.Identifier(cfg["table"])))
        columns = [d[0] for d in cur.description]
    except Exception as e:
        # cannot connect to DB -> render placeholders
        try:
            add_notification("DB connection error", str(e))
        except Exception:
            pass
        columns = ["col1", "col2", "col3"]
        rows = [(None, None, None) for _ in range(10)]
        page = 1
        total_pages = 1
        total_logs = 0
        filters = load_filters() or {}
        ai_model = (load_settings() or {}).get("model")

        return templates.TemplateResponse("index.html", {
            "request": request,
            "rows": rows,
            "columns": columns,
            "page": page,
            "total_pages": total_pages,
            "total_logs": total_logs,
            "sort": sort,
            "order": order,
            "level": level,
            "q": q,
            "filters_keys": ["all"] + sorted(k.lower() for k in filters.keys()),
            "filters": {k.lower(): v for k, v in filters.items()},
            "ai_model": ai_model,
            "db_connected": False
        })

    if sort not in columns:
        sort = columns[0]
    if order not in ("asc", "desc"):
        order = "desc"

    filters = load_filters()
    default_keywords_map = {
        "error": ["error", "failed", "denied", "panic"],
        "warn": ["warn", "timeout", "retry"],
        "info": ["info", "started", "connected"],
    }
    if not filters:
        filters = default_keywords_map

    allowed_levels = ["all"] + sorted(k.lower() for k in filters.keys())
    level = level.strip().lower()
    if level not in allowed_levels:
        level = "all"

    q = q.strip()
    where_clauses = []
    params = []

    if level != "all":
        keywords = []
        for k, v in filters.items():
            if k.strip().lower() == level:
                if isinstance(v, dict):
                    keywords = v.get("words", [])
                else:
                    keywords = v
                break
        if keywords:
            level_conditions = []
            for col in columns:
                for kw in keywords:
                    level_conditions.append(sql.SQL("CAST({} AS TEXT) ILIKE %s").format(sql.Identifier(col)))
                    params.append(f"%{kw}%")
            where_clauses.append(sql.SQL("(") + sql.SQL(" OR ").join(level_conditions) + sql.SQL(")"))

    if q:
        search_conditions = []
        for col in columns:
            search_conditions.append(sql.SQL("CAST({} AS TEXT) ILIKE %s").format(sql.Identifier(col)))
            params.append(f"%{q}%")
        where_clauses.append(sql.SQL("(") + sql.SQL(" OR ").join(search_conditions) + sql.SQL(")"))

    where_sql = sql.SQL("")
    if where_clauses:
        where_sql = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_clauses)

    count_query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(cfg["table"])) + where_sql
    cur.execute(count_query, params)
    total_logs = cur.fetchone()[0]

    settings = load_settings()
    logs_per_page = int(settings.get("logs_per_page", LOGS_PER_PAGE))
    total_pages = max(1, ceil(total_logs / logs_per_page))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * logs_per_page

    query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(cfg["table"])) + where_sql + sql.SQL(" ORDER BY {} {} LIMIT %s OFFSET %s").format(sql.Identifier(sort), sql.SQL(order.upper()))
    cur.execute(query, params + [logs_per_page, offset])
    rows = cur.fetchall()

    cur.close()
    conn.close()

    ai_model = settings.get("model")

    return templates.TemplateResponse("index.html", {
        "request": request,
        "rows": rows,
        "columns": columns,
        "page": page,
        "total_pages": total_pages,
        "total_logs": total_logs,
        "sort": sort,
        "order": order,
        "level": level,
        "q": q,
        "filters_keys": ["all"] + sorted(k.lower() for k in filters.keys()),
        "filters": {k.lower(): v for k, v in filters.items()},
        "ai_model": ai_model
    })


@router.get("/log/{log_id}", response_class=HTMLResponse)
def log_detail(request: Request, log_id: str):
    cfg = load_config()
    if not cfg or "table" not in cfg:
        return RedirectResponse("/connect", status_code=303)

    conn = get_logs_conn(cfg)
    ensure_solution_table(conn)
    cur = conn.cursor()

    cur.execute(sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(cfg["table"])), (log_id,))
    log_row = cur.fetchone()
    if not log_row:
        cur.close()
        conn.close()
        return HTMLResponse("Р›РѕРі РЅРµ РЅР°Р№РґРµРЅ", status_code=404)

    columns = [desc[0] for desc in cur.description]
    cur.execute("""
        SELECT solution, source, created_at
        FROM log_solutions
        WHERE table_name=%s AND log_id=%s
        ORDER BY created_at DESC
    """, (cfg["table"], log_id))
    solutions = cur.fetchall()

    cur.close()
    conn.close()

    # include AI model for client-side checks
    settings = load_settings()
    ai_model = settings.get("model")
    return templates.TemplateResponse("log_detail.html", {"request": request, "columns": columns, "log_row": log_row, "solutions": solutions, "log_id": log_id, "ai_model": ai_model})


@router.post("/add_solution")
def add_solution(log_id: str = Form(...), solution: str = Form(...)):
    cfg = load_config()
    conn = get_logs_conn(cfg)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO log_solutions (table_name, log_id, solution, source)
        VALUES (%s, %s, %s, 'manual')
    """, (cfg["table"], log_id, solution))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(f"/log/{log_id}", status_code=303)


@router.post("/ai_solution")
def ai_solution(log_id: str, mode: str = "reasoning"):
    cfg = load_config()
    conn = get_logs_conn(cfg)
    cur = conn.cursor()
    cur.execute(sql.SQL("SELECT * FROM {} WHERE id=%s").format(sql.Identifier(cfg["table"])), (log_id,))
    row = cur.fetchone()
    columns = [d[0] for d in cur.description]
    cur.close()
    conn.close()
    if not row:
        return {"error": "Р›РѕРі РЅРµ РЅР°Р№РґРµРЅ"}
    log_text = "\n".join(f"{columns[i]}: {row[i]}" for i in range(len(columns)))
    try:
        settings = load_settings()
        model = settings.get("model")
        ai_options = settings.get("ai_options") or {}
        ai_provider = (settings.get("ai_provider") or "ollama").strip().lower()
        if not model:
            # log attempt and inform client
            try:
                add_notification("AI request blocked", "User attempted AI generation but no model is configured")
            except Exception:
                pass
            return JSONResponse(status_code=400, content={"error": "РР РЅРµ РЅР°СЃС‚СЂРѕРµРЅ. РћС‚РєСЂРѕР№С‚Рµ РЅР°СЃС‚СЂРѕР№РєРё."})

        use_mode = (mode or "reasoning").strip().lower()
        enable_thinking = use_mode != "fast"
        answer = generate_solution(
            log_text,
            timeout=300,
            model=model,
            provider=ai_provider,
            options=ai_options,
            enable_thinking=enable_thinking,
        )
        return {"text": answer}
    except Exception as e:
        try:
            add_notification("AI generation error", str(e))
        except Exception:
            pass
        return JSONResponse(status_code=200, content={"error": f"РћС€РёР±РєР° РіРµРЅРµСЂР°С†РёРё: {str(e)}"})



