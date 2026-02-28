import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:4b"


def get_available_models(timeout: int = 2):
    """
    Try to query local Ollama for available models.
    Returns a list of model names. On failure, returns a list with the default MODEL.
    """
    try:
        resp = requests.get(OLLAMA_URL.replace("/api/generate", "/api/models"), timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Ollama returns list of objects with 'name' or simple names depending on version
        models = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "name" in item:
                    models.append(item["name"])
                elif isinstance(item, str):
                    models.append(item)
        if not models:
            models = [MODEL]
        return models
    except Exception:
        return [MODEL]


def stream_thinking(prompt: str, timeout: int = 300, model: str = None):
    print("\n" + "=" * 80)
    print("🧠 AI THINKING (stream)")
    print("=" * 80)

    with requests.post(
        OLLAMA_URL,
        json={"model": model or MODEL, "prompt": prompt, "stream": True},
        stream=True,
        timeout=timeout  # теперь параметр используется
    ) as r:
        r.raise_for_status()

        full = ""
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line.decode())
            chunk = data.get("response", "")
            print(chunk, end="", flush=True)
            full += chunk
            if data.get("done"):
                break

    print("\n\n🧠 THINKING DONE\n")
    return full


def generate_solution(log_text: str, timeout=300, model: str = None):
    # 1. thinking — вывод в терминал, без блокировки сайта
    thinking_model = model or MODEL
    # streaming thinking uses the same endpoint but with stream=True; reuse prompt
    stream_thinking(
        f"Разбери лог и найди возможную причину проблемы:\n{log_text}",
        timeout=timeout,
        model=thinking_model
    )

    # 2. финальный ответ — в textarea
    return generate_final_answer(log_text, timeout=timeout, model=thinking_model)


def generate_final_answer(log_text: str, timeout=300, model: str = None) -> str:
    prompt = f"""
Ты опытный DevOps инженер.
На основе лога дай КОРОТКОЕ и ЧЁТКОЕ решение (1–2 предложения).
Без рассуждений. Без объяснений. Без размышлений.

ЛОГ:
{log_text}
"""
    use_model = model or MODEL
    with requests.post(
        OLLAMA_URL,
        json={"model": use_model, "prompt": prompt, "stream": False},
        timeout=timeout  # увеличенный таймаут
    ) as r:
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()

