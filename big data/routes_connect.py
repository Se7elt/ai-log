from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_logs_conn, ensure_solution_table
from config import save_config, load_config, add_notification
import psycopg2
from psycopg2 import sql

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/connect", response_class=HTMLResponse)
def connect_form(request: Request):
    return templates.TemplateResponse("connect.html", {"request": request})


@router.post("/connect")
def connect_db(
    host: str = Form(...),
    port: int = Form(...),
    dbname: str = Form(...),
    user: str = Form(...),
    password: str = Form(...)
):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        conn.close()
    except Exception as e:
        add_notification("DB connection error", str(e))
        return RedirectResponse("/connect", status_code=303)

    save_config({
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
        "password": password
    })

    add_notification("DB connected", f"{user}@{host}:{port}/{dbname}")

    return RedirectResponse("/tables", status_code=303)


@router.get("/tables", response_class=HTMLResponse)
def list_tables(request: Request):
    cfg = load_config()
    if not cfg:
        return RedirectResponse("/connect", status_code=303)

    conn = get_logs_conn(cfg)
    cur = conn.cursor()

    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
        ORDER BY table_name
    """)
    tables = cur.fetchall()

    cur.close()
    conn.close()

    return templates.TemplateResponse("tables.html", {"request": request, "tables": tables})


@router.get("/preview/{table}", response_class=HTMLResponse)
def preview_table(request: Request, table: str):
    cfg = load_config()
    if not cfg:
        return RedirectResponse("/connect", status_code=303)

    conn = get_logs_conn(cfg)
    cur = conn.cursor()

    cur.execute(
        sql.SQL("SELECT * FROM {} LIMIT 20").format(sql.Identifier(table))
    )

    rows = cur.fetchall()
    columns = [d[0] for d in cur.description]

    cur.close()
    conn.close()

    return templates.TemplateResponse("preview.html", {"request": request, "rows": rows, "columns": columns, "table": table})


@router.post("/use_table")
def use_table(table: str = Form(...)):
    cfg = load_config()
    cfg["table"] = table
    save_config(cfg)

    conn = get_logs_conn(cfg)
    ensure_solution_table(conn)
    conn.close()

    return RedirectResponse("/", status_code=303)

