"""MCP tool test uçları — mcp_server.TOOLS kayıt defterinden OTOMATİK üretilir.

Eskiden her tool için burada elle bir pydantic modeli + endpoint yazılıyordu
(tanım kayması riski, dış analizde P2 borç). Artık tek kayıt kaynağı var:
mcp_server'daki @tool dekoratörü. Bu modül her kayıtlı tool için imzasından
dinamik bir pydantic modeli türetir (tip doğrulama + Swagger şeması korunur)
ve POST /api/mcp/<ad> ucunu açar; parametresiz tool'lar için GET de açılır
(eski istemcilerle geriye dönük uyum: list_collections, list_domain_models).
Parite güvencesi: tests/test_api.py::test_mcp_rest_parity."""
import inspect

from fastapi import APIRouter
from pydantic import create_model

try:
    from .. import mcp_server
except ImportError:
    import mcp_server

router = APIRouter()


def _model_for(name: str, fn) -> type | None:
    """Tool imzasından pydantic istek modeli türetir; hiç parametre yoksa None."""
    fields = {}
    for pname, p in inspect.signature(fn).parameters.items():
        ann = p.annotation if p.annotation is not inspect.Parameter.empty else str
        default = p.default if p.default is not inspect.Parameter.empty else ...
        fields[pname] = (ann, default)
    if not fields:
        return None
    return create_model(f"Mcp_{name}", **fields)


def _register(name: str, fn):
    Model = _model_for(name, fn)
    if Model is None:
        # parametresiz tool: GET (geriye dönük uyum) + POST
        def endpoint_noargs():
            return fn()
        endpoint_noargs.__name__ = f"mcp_{name}"
        router.add_api_route(f"/api/mcp/{name}", endpoint_noargs, methods=["GET", "POST"])
        return

    def endpoint(r: Model):   # type: ignore[valid-type]
        return fn(**r.model_dump())
    endpoint.__name__ = f"mcp_{name}"
    router.add_api_route(f"/api/mcp/{name}", endpoint, methods=["POST"])


for _name, _fn in mcp_server.TOOLS.items():
    _register(_name, _fn)
