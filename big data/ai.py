import json
import subprocess
import requests

DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "qwen3:4b"
OLLAMA_BASE_URL = "http://localhost:11434"
LM_STUDIO_BASE_URL = "http://localhost:1234"


def get_providers():
    return [
        {"value": "ollama", "label": "Ollama"},
        {"value": "lmstudio", "label": "LM Studio"},
    ]


def _parse_model_names(data):
    models = []
    if isinstance(data, dict):
        if isinstance(data.get("models"), list):
            data = data["models"]
        elif isinstance(data.get("data"), list):
            data = data["data"]

    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("id") or item.get("model")
                if name:
                    models.append(name)

    unique = []
    seen = set()
    for model in models:
        if model not in seen:
            seen.add(model)
            unique.append(model)
    return unique


def _get_ollama_models(timeout: int = 2):
    endpoints = ["/api/models", "/api/tags"]
    for endpoint in endpoints:
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL}{endpoint}", timeout=timeout)
            resp.raise_for_status()
            models = _parse_model_names(resp.json())
            if models:
                return models
        except Exception:
            continue
    return [DEFAULT_MODEL]


def _get_lmstudio_models(timeout: int = 2):
    endpoints = [
        "/api/v0/models",
        "/api/v0/models?state=downloaded",
        "/api/v0/models?status=downloaded",
        "/v1/models",
    ]
    for endpoint in endpoints:
        try:
            resp = requests.get(f"{LM_STUDIO_BASE_URL}{endpoint}", timeout=timeout)
            resp.raise_for_status()
            models = _parse_model_names(resp.json())
            if models:
                return models
        except Exception:
            continue

    try:
        proc = subprocess.run(
            ["lms", "ls", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
            check=True,
        )
        models = _parse_model_names(json.loads(proc.stdout or "[]"))
        if models:
            return models
    except Exception:
        pass

    return [DEFAULT_MODEL]


def get_available_models(provider: str = DEFAULT_PROVIDER, timeout: int = 2):
    provider = (provider or DEFAULT_PROVIDER).strip().lower()
    if provider == "lmstudio":
        return _get_lmstudio_models(timeout=timeout)
    return _get_ollama_models(timeout=timeout)


def _build_ollama_options(options: dict | None):
    if not options:
        return None
    mapping = {
        "context_length": "num_ctx",
        "gpu_offload": "num_gpu",
        "cpu_threads": "num_thread",
        "eval_batch_size": "num_batch",
        "temperature": "temperature",
    }
    out = {}
    for key, target in mapping.items():
        val = options.get(key)
        if val is None or val == "":
            continue
        out[target] = val
    return out or None


def stream_thinking(
    prompt: str,
    timeout: int = 300,
    model: str = None,
    provider: str = DEFAULT_PROVIDER,
    options: dict | None = None,
):
    print("\n" + "=" * 80)
    print("AI THINKING (stream)")
    print("=" * 80)

    use_model = model or DEFAULT_MODEL
    use_provider = (provider or DEFAULT_PROVIDER).strip().lower()
    full = ""

    if use_provider == "lmstudio":
        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if options and options.get("temperature") is not None:
            payload["temperature"] = options["temperature"]
        with requests.post(
            f"{LM_STUDIO_BASE_URL}/v1/chat/completions",
            json=payload,
            stream=True,
            timeout=timeout,
        ) as r:
            r.raise_for_status()
            for raw_line in r.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    chunk = delta.get("content", "")
                except Exception:
                    chunk = ""
                if chunk:
                    print(chunk, end="", flush=True)
                    full += chunk
    else:
        payload = {"model": use_model, "prompt": prompt, "stream": True}
        ollama_options = _build_ollama_options(options)
        if ollama_options:
            payload["options"] = ollama_options
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            stream=True,
            timeout=timeout,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line.decode())
                chunk = data.get("response", "")
                print(chunk, end="", flush=True)
                full += chunk
                if data.get("done"):
                    break

    print("\n\nTHINKING DONE\n")
    return full


def generate_solution(
    log_text: str,
    timeout=300,
    model: str = None,
    provider: str = DEFAULT_PROVIDER,
    options: dict | None = None,
    enable_thinking: bool = True,
):
    thinking_model = model or DEFAULT_MODEL
    thinking_result = ""
    mode = "reasoning" if enable_thinking else "fast"
    
    if enable_thinking:
        # Сохраняем результат мышления
        thinking_result = stream_thinking(
            (
                "Разбери лог. "
                "1) Определи систему/инструмент (IDE, сервис, ОС). "
                "2) Найди корневую причину. "
                "3) Сформулируй краткий план исправления.\n\n"
                f"ЛОГ:\n{log_text}"
            ),
            timeout=timeout,
            model=thinking_model,
            provider=provider,
            options=options,
        )

    # Передаем мысли в финальный ответ
    return generate_final_answer(
        log_text, 
        thinking_context=thinking_result,  # ← Ключевое изменение
        timeout=timeout, 
        model=thinking_model, 
        provider=provider, 
        options=options,
        mode=mode,
    )


def generate_final_answer(
    log_text: str,
    thinking_context: str = "",
    timeout=300,
    model: str = None,
    provider: str = DEFAULT_PROVIDER,
    options: dict | None = None,
    mode: str = "reasoning",
) -> str:
    mode = (mode or "reasoning").strip().lower()
    is_fast = mode == "fast"

    # Формируем промпт с контекстом (только для reasoning)
    context_block = (
        f"\n\nМОИ РАЗМЫШЛЕНИЯ:\n{thinking_context}" if (thinking_context and not is_fast) else ""
    )

    if is_fast:
        prompt = f"""
Ты опытный DevOps инженер, анализируешь логи.
Дай краткое решение (1-2 предложения максимум).

ТРЕБОВАНИЯ:
1. Сначала укажи источник ошибки (IDE, сервис, ОС, приложение).
2. Затем — одно конкретное действие для исправления.
3. Максимальная краткость, без пояснений и рассуждений.

ЛОГ:
{log_text}
"""
    else:
        prompt = f"""
Ты опытный DevOps инженер, анализируешь логи.
Дай короткое решение (2-3 предложения максимум).

ТРЕБОВАНИЯ:
1. Сначала укажи источник ошибки (IDE, сервис, ОС, приложение).
2. Затем — конкретное действие для исправления.
3. Без воды, но с контекстом.

ЛОГ:{context_block}

{log_text}
"""
    use_model = model or DEFAULT_MODEL
    use_provider = (provider or DEFAULT_PROVIDER).strip().lower()

    if use_provider == "lmstudio":
        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if options and options.get("temperature") is not None:
            payload["temperature"] = options["temperature"]
        with requests.post(
            f"{LM_STUDIO_BASE_URL}/v1/chat/completions",
            json=payload,
            timeout=timeout,
        ) as r:
            r.raise_for_status()
            data = r.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    payload = {"model": use_model, "prompt": prompt, "stream": False}
    ollama_options = _build_ollama_options(options)
    if ollama_options:
        payload["options"] = ollama_options
    with requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=timeout,
    ) as r:
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()
