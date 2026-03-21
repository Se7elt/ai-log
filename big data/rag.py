import json
from pathlib import Path
from typing import List, Tuple
import requests

DEFAULT_EMBED_MODEL = ""
LM_STUDIO_BASE_URL = "http://localhost:1234"
DOCS_DIR = Path("rag_docs")
INDEX_FILE = Path("rag_index.json")


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(len(a)):
        av = a[i]
        bv = b[i]
        dot += av * bv
        na += av * av
        nb += bv * bv
    if na == 0.0 or nb == 0.0:
        return -1.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def _chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> List[str]:
    text = text.replace("\r\n", "\n")
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end]
        chunks.append(chunk)
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _embed_texts(
    texts: List[str],
    model: str,
    base_url: str,
    timeout: int = 120,
    batch_size: int = 16,
) -> List[List[float]]:
    if not model:
        raise ValueError("Embedding model is not configured")
    out: List[List[float]] = []
    if not texts:
        return out
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        payload = {
            "model": model,
            "input": batch,
        }
        r = requests.post(f"{base_url}/v1/embeddings", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        for item in data.get("data", []):
            out.append(item.get("embedding", []))
    return out


def _load_index():
    if not INDEX_FILE.exists():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(items: list):
    INDEX_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def reindex_documents(
    embedding_model: str,
    base_url: str = LM_STUDIO_BASE_URL,
    max_chunk_chars: int = 1200,
    overlap: int = 200,
):
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in DOCS_DIR.glob("**/*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".txt", ".md"):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            try:
                raw = path.read_text(encoding="cp1251")
            except Exception:
                continue
        chunks = _chunk_text(raw, max_chars=max_chunk_chars, overlap=overlap)
        if not chunks:
            continue
        embeddings = _embed_texts(chunks, model=embedding_model, base_url=base_url)
        for i, chunk in enumerate(chunks):
            emb = embeddings[i] if i < len(embeddings) else []
            items.append({
                "source": str(path.name),
                "text": chunk,
                "embedding": emb,
            })
    _save_index(items)
    return len(items)


def retrieve_context(
    query: str,
    embedding_model: str,
    base_url: str = LM_STUDIO_BASE_URL,
    top_k: int = 4,
    max_total_chars: int = 2000,
) -> str:
    items = _load_index()
    if not items:
        return ""
    q_emb = _embed_texts([query], model=embedding_model, base_url=base_url)
    if not q_emb:
        return ""
    q_emb = q_emb[0]
    scored: List[Tuple[float, dict]] = []
    for item in items:
        score = _cosine(q_emb, item.get("embedding", []))
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)

    out_parts = []
    total = 0
    for score, item in scored[: max(1, top_k)]:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        chunk = f"[SOURCE: {item.get('source','unknown')}]\n{text}\n"
        if total + len(chunk) > max_total_chars:
            break
        out_parts.append(chunk)
        total += len(chunk)

    return "\n".join(out_parts).strip()
