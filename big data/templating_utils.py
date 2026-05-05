from __future__ import annotations

import inspect
from typing import Any, Dict


def render_template(templates: Any, request: Any, name: str, context: Dict[str, Any]):
    """
    Starlette/Jinja2Templates.TemplateResponse signature changed across versions.

    Old (Starlette <=0.27-ish):
        templates.TemplateResponse(request, name, context)

    New:
        templates.TemplateResponse(name, context) where context MUST contain "request".

    This helper makes the app work across both variants.
    """

    # Defensive: don't mutate caller dict.
    ctx = dict(context or {})

    try:
        sig = inspect.signature(templates.TemplateResponse)
        params = list(sig.parameters.values())
    except Exception:
        params = []

    # If the first parameter is named "request" (old API), call old-style.
    if params and params[0].name == "request":
        return templates.TemplateResponse(request, name, ctx)

    # Otherwise assume new-style API.
    ctx.setdefault("request", request)
    return templates.TemplateResponse(name, ctx)

