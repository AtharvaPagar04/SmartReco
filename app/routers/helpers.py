from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.csrf import ensure_csrf_token
from app.flash import pop_flashes

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def page(request: Request, name: str, **context):
    context.update(csrf_token=ensure_csrf_token(request), flashes=pop_flashes(request), request=request)
    return templates.TemplateResponse(request=request, name=name, context=context)
