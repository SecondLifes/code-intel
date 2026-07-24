"""MCP tool test uçları — mcp_server'daki GERÇEK tool fonksiyonlarını REST'ten çağırır
(aynı kod yolu, kopya yok; bkz. tests/test_api.py parite sözleşme testi)."""
from fastapi import APIRouter
from pydantic import BaseModel

try:
    from .. import mcp_server
except ImportError:
    import mcp_server

router = APIRouter()

class McpSearchReq(BaseModel):
    query: str; collections: list[str] | None = None; mode: str = "hybrid"; top_k: int = 8; offset: int = 0
    kind: str = ""; unit: str = ""; rerank: bool = False

@router.post("/api/mcp/search_code")
def mcp_search_code(r: McpSearchReq):
    return mcp_server.search_code(r.query, r.collections, r.mode, r.top_k, r.offset,
                                   kind=r.kind, unit=r.unit, rerank=r.rerank)

class McpChunkReq(BaseModel):
    collection: str; id: int

@router.post("/api/mcp/get_chunk")
def mcp_get_chunk(r: McpChunkReq):
    return mcp_server.get_chunk(r.collection, r.id)

class McpExplainReq(BaseModel):
    collection: str; id: int; depth: str = "fast"

@router.post("/api/mcp/explain_chunk")
def mcp_explain_chunk(r: McpExplainReq):
    return mcp_server.explain_chunk(r.collection, r.id, r.depth)

@router.post("/api/mcp/review_code")
def mcp_review_code(r: McpChunkReq):
    return mcp_server.review_code(r.collection, r.id)

class McpDomainReq(BaseModel):
    question: str; domain: str; code_context: str = ""

@router.post("/api/mcp/ask_domain_model")
def mcp_ask_domain_model(r: McpDomainReq):
    return mcp_server.ask_domain_model(r.question, r.domain, r.code_context)

@router.get("/api/mcp/list_domain_models")
def mcp_list_domain_models():
    return mcp_server.list_domain_models()

@router.get("/api/mcp/list_collections")
def mcp_list_collections():
    return mcp_server.list_collections()

@router.post("/api/mcp/get_relations")
def mcp_get_relations(r: McpChunkReq):
    return mcp_server.get_relations(r.collection, r.id)

class McpSimilarReq(BaseModel):
    collection: str; id: int; top_k: int = 8

@router.post("/api/mcp/find_similar")
def mcp_find_similar(r: McpSimilarReq):
    return mcp_server.find_similar(r.collection, r.id, r.top_k)

class McpUnitReq(BaseModel):
    collection: str; unit: str

@router.post("/api/mcp/read_unit")
def mcp_read_unit(r: McpUnitReq):
    return mcp_server.read_unit(r.collection, r.unit)

class McpImpactReq(BaseModel):
    collection: str; base: str = ""

@router.post("/api/mcp/analyze_impact")
def mcp_analyze_impact(r: McpImpactReq):
    return mcp_server.analyze_impact(r.collection, r.base)

class McpTypeReq(BaseModel):
    collection: str; type_name: str

@router.post("/api/mcp/get_type_hierarchy")
def mcp_get_type_hierarchy(r: McpTypeReq):
    return mcp_server.get_type_hierarchy(r.collection, r.type_name)

class McpRefsReq(BaseModel):
    collection: str; name: str; top_k: int = 30

@router.post("/api/mcp/find_references")
def mcp_find_references(r: McpRefsReq):
    return mcp_server.find_references(r.collection, r.name, r.top_k)
