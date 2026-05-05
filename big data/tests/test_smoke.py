import json
from pathlib import Path
import requests
import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
RAG_INDEX_PATH = ROOT / "rag_index.json"


def test_db_access():
    if not CONFIG_PATH.exists():
        pytest.skip("config.json is not present (expected in local dev only)")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row and row[0] == 1


def test_ollama_models_available():
    urls = [
        "http://localhost:11434/api/tags",
        "http://localhost:11434/api/models",
    ]
    last_error = None
    for url in urls:
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            # Accept list or dict with models
            if isinstance(data, dict) and isinstance(data.get("models"), list):
                assert len(data["models"]) > 0
                return
            if isinstance(data, list):
                assert len(data) > 0
                return
        except Exception as e:
            last_error = e
            continue
    pytest.skip(f"Ollama is not available on localhost: {last_error}")


def test_lmstudio_models_available():
    urls = [
        "http://localhost:1234/api/v0/models",
        "http://localhost:1234/v1/models",
    ]
    last_error = None
    for url in urls:
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                assert len(data["data"]) > 0
                return
            if isinstance(data, dict) and isinstance(data.get("models"), list):
                assert len(data["models"]) > 0
                return
            if isinstance(data, list):
                assert len(data) > 0
                return
        except Exception as e:
            last_error = e
            continue
    pytest.skip(f"LM Studio is not available on localhost: {last_error}")


def test_rag_index_exists_and_not_empty():
    if not RAG_INDEX_PATH.exists():
        pytest.skip("rag_index.json is not present (generated locally after indexing docs)")
    data = json.loads(RAG_INDEX_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) > 0
