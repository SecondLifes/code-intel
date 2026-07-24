"""Code-Intel MCP sunucusu — stdio üzerinden Claude Code, Codex CLI, Gemini CLI
gibi MCP-uyumlu ajanlara Delphi kod tabanı arama/açıklama/inceleme araçları sunar.
16 tool: search_code, get_chunk, get_relations, find_similar, read_unit,
get_type_hierarchy, find_references, get_unit_deps, get_context_pack, analyze_impact, document_unit, explain_chunk, review_code,
ask_domain_model, list_domain_models, list_collections.

Çalıştır:  .venv/Scripts/python.exe -m src.mcp_server
(Claude Code / Codex / Gemini CLI'nin kendi MCP client ayarına bu komutu ekleyin.)

Otonom DEĞİLDİR — hiçbir tool arka planda kendiliğinden çalışmaz, sadece çağıran
ajan açıkça bir tool'u çağırınca iş yapar. Kod ÜRETMEZ — review_code bile sadece
mevcut kodu eleştirir, yeni kod yazmaz.

Ayarlar mcp-config.json'dan okunur (proje kökü) — model isimleri, Qdrant/Ollama
adresleri, alan-özel (domain) model eşlemesi.
"""
import json
import pathlib

from mcp.server.fastmcp import FastMCP

try:
    from . import retrieval
except ImportError:
    import retrieval

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "mcp-config.json"

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}

CFG = load_config()
DEFAULT_COLLECTIONS = CFG.get("default_collections", ["unidac"])
FAST_MODEL = CFG.get("fast_model", "gemma4:12b")
DEEP_MODEL = CFG.get("deep_model", "qwen3.6")
DOMAIN_MODELS = {k: v for k, v in CFG.get("domain_models", {}).items() if not k.startswith("$")}

mcp = FastMCP("code-intel")

# ---------------- TOOL REGISTRY (tek kayıt kaynağı) ----------------
# Her tool @tool ile TEK kez tanımlanır: hem FastMCP'ye (stdio MCP client'ları)
# hem TOOLS sözlüğüne kaydolur. api/mcp_routes.py REST test uçlarını bu
# sözlükten OTOMATİK üretir — eskiden her tool 4 yerde elle çoğaltılıyordu
# (mcp_server + panel pydantic modeli + endpoint + api.html), tanım kayması
# riski dış analizde P2 borç olarak işaretlenmişti. Parite artık yapısal olarak
# garantili; tests/test_api.py'deki sözleşme testi güvence olarak duruyor.
TOOLS: dict[str, object] = {}

def tool(fn):
    TOOLS[fn.__name__] = fn
    return mcp.tool()(fn)

@tool
def search_code(query: str, collections: list[str] | None = None, mode: str = "hybrid", top_k: int = 8,
                 offset: int = 0, kind: str = "", unit: str = "", rerank: bool = False,
                 expand: bool = False, lang: str = "") -> dict:
    """Kod tabanında hibrit (anlamsal+kelime, ağırlıklı RRF + isim-eşleşme
    boost'uyla birleştirilmiş) arama yapar. Delphi/Pascal ile başladı; artık
    Python/C#/C-C++/Java/Go/Rust'ta da tam derinlikte (doc, çağrı grafiği,
    kalıtım), ~45 başka dilde temel seviyede (chunk+isim+arama) çalışır.

    query: Türkçe veya İngilizce doğal dil sorgusu (örn. "bağlantı stringi nasıl parse edilir").
    collections: aranacak indeks adları (boşsa yapılandırmadaki varsayılan(lar) kullanılır).
    mode: "hybrid" (önerilen), "dense" (sadece anlamsal), "sparse" (sadece kelime).
    top_k: kaç sonuç döndürülsün. offset: sayfalama için kaç sonuç atlanacak.
    kind: "method" (sadece gövdeler) | "decl" (sadece bildirimler) | "type" (sadece
    tip tanımları) | "" (hepsi). unit: dosya yolu alt-dize filtresi (örn. "Providers/").
    lang: "" (hepsi) | "pascal" | "python" | "csharp" | "cpp" | "java" | "go" | "rust" | ...
    (list_collections'daki koleksiyon karışıksa aramayı tek dile daraltmak için).
    rerank: True ise en iyi 50 aday cross-encoder ile yeniden sıralanır — daha
    isabetli sıra, biraz daha yavaş (ilk çağrıda model yüklenir).

    Döndürür: total (bu çalıştırmada elenen aday sayısı), has_more, ve her biri
    collection, score, id, unit (dosya), name (method/tip adı), line_start/line_end,
    lang, code (kısaltılmış), doc (varsa doc özeti) içeren hit listesi. Aynı
    rutinin decl+method kopyaları tekilleştirilir (method tutulur).
    """
    return retrieval.search(query, collections or DEFAULT_COLLECTIONS, mode, top_k, offset,
                            kind=kind, unit=unit, rerank=rerank, expand=expand, lang=lang)

@tool
def find_similar(collection: str, id: int, top_k: int = 8) -> dict:
    """Verilen chunk'a anlamsal olarak EN BENZER diğer kod parçalarını bulur —
    "buna benzer başka implementasyon var mı?", tekrarlanan/kopyalanmış mantık
    tespiti, alternatif kullanım örnekleri için. Chunk'ın kayıtlı dense vektörü
    kullanılır (yeniden embedding hesaplanmaz), kendisi sonuçlardan çıkarılır."""
    return retrieval.find_similar(collection, id, top_k)

@tool
def read_unit(collection: str, unit: str) -> dict:
    """Bir dosyanın (unit, tam göreli yol — örn. "Source/Utils.pas") indekslenmiş
    TÜM chunk'larını satır sırasına dizip birleştirilmiş kodu döndürür — dosyanın
    bütününü tek çağrıda görmek için. YAKLAŞIK bir yeniden kurgudur: chunk'lanmamış
    aralar (uses listesi, global tanımlar) dahil değildir. Her parçanın başına
    `// [kind] name (Lx-Ly, id=...)` satırı eklenir; id'ler get_chunk/get_relations
    ile derinleşmek için kullanılabilir."""
    return retrieval.read_unit(collection, unit)

@tool
def get_chunk(collection: str, id: int) -> dict:
    """Belirli bir chunk'ın TAM (kısaltılmamış) kaynak kodunu ve tüm meta verisini getirir.
    search_code bir sonucu kısaltarak döndürür — bu tool tam metni ister."""
    result = retrieval.get_chunk(collection, id, full_code=True)
    return result or {"error": f"chunk bulunamadı: {collection}/{id}"}

@tool
def get_relations(collection: str, id: int) -> dict:
    """Bir kod parçasının çağrı ilişkilerini döndürür: calls (bu parçanın çağırdığı
    metodlar), called_by (bu parçayı çağıran metodlar), same_unit (aynı dosyadaki
    diğer parçalar). ÖNEMLİ: calls/called_by isim-tabanlı bir SEZGİYLE çözülür —
    gerçek tip/overload çözümlemesi yapılmaz, aynı isimde birden fazla metot varsa
    (aşırı yükleme, farklı sınıflarda aynı isim) hepsi aday olarak listelenir; bu
    yüzden "kesin çağrı grafiği" değil, "olası ilişkiler" olarak değerlendirilmeli."""
    return retrieval.get_relations(collection, id)

@tool
def explain_chunk(collection: str, id: int, depth: str = "fast") -> dict:
    """Bir kod parçasını Türkçe açıklar. depth="fast": kısa (varsa /// doc özetinin
    doğrudan çevirisi, ucuz/hızlı). depth="deep": kodun tam mantık akışı, kenar
    durumlar ve olası riskler dahil derin analiz (daha yavaş, daha güçlü model).
    Sonuç kalıcı önbelleklenir — aynı chunk+depth için tekrar çağrı anında döner."""
    model = FAST_MODEL if depth == "fast" else DEEP_MODEL
    return retrieval.explain_chunk(collection, id, depth, model)

@tool
def review_code(collection: str, id: int) -> dict:
    """Mevcut bir kod parçasını hata/risk için inceler (code review) — bellek
    sızıntısı, nil/null kontrolü eksikliği, exception güvenliği, kaynak kapatma,
    mantık hatası gibi somut sorunları Türkçe raporlar. İSTEK ÜZERİNE çalışır
    (otonom/arka plan DEĞİL), YENİ KOD ÜRETMEZ — sadece mevcut kodu değerlendirir."""
    return retrieval.review_chunk(collection, id, DEEP_MODEL)

@tool
def ask_domain_model(question: str, domain: str, code_context: str = "") -> dict:
    """Belirli bir alanda (örn. "sql") özel olarak eğitilmiş, ayrıca kurulu bir
    Ollama modeline doğrudan soru sorar — varsayılan model o alanda zayıf kalırsa
    (örn. karmaşık bir SQL sorgusunu doğru açıklayamazsa) karşılaştırma/alternatif
    yanıt almak için kullanılır. Hangi alanların tanımlı olduğunu görmek için
    domain'i boş bırakın veya list_domain_models'ı çağırın."""
    model = DOMAIN_MODELS.get(domain.lower())
    if not model:
        return {"error": f'"{domain}" için tanımlı bir model yok. Tanımlılar: {list(DOMAIN_MODELS.keys())} '
                          f"(mcp-config.json içindeki domain_models'a ekleyebilirsiniz)."}
    prompt = question if not code_context else f"{question}\n\nBAĞLAM (kod):\n{code_context}"
    txt = retrieval.ollama_generate(model, prompt, num_predict=700)
    return {"model": model, "domain": domain, "answer": txt}

@tool
def get_type_hierarchy(collection: str, type_name: str) -> dict:
    """Bir Delphi tipinin kalıtım hiyerarşisini döndürür: ancestors (üst sınıf
    zinciri, köke doğru), descendants (alt sınıflar, 2 seviye), implements (bu
    sınıfın uyguladığı interface'ler), implementers (bu interface'i uygulayan
    sınıflar). in_corpus=false olan atalar korpus dışıdır (örn. TObject, RTL
    sınıfları). Kenarlar indeksleme sırasında tip bildirimlerinden çıkarılır —
    isim tabanlıdır, chunk_id'lerle get_chunk'a derinleşilebilir."""
    return retrieval.get_type_hierarchy(collection, type_name)

@tool
def find_references(collection: str, name: str, top_k: int = 30) -> dict:
    """Bir sembol adının korpustaki izlerini üç grupta döndürür: definitions
    (adı birebir taşıyan chunk'lar), callers (bu tanımları çağıran metodlar,
    isim-sezgili çağrı grafiğinden), textual (adın kelime aramasında geçtiği
    diğer chunk'lar — yorum/string içi olabilir). TAM statik analiz değildir;
    tip hiyerarşisi için ayrıca get_type_hierarchy kullanın."""
    return retrieval.find_references(collection, name, top_k)

@tool
def analyze_impact(collection: str, base: str = "", head: str = "HEAD") -> dict:
    """Değişiklik etki analizi: koleksiyonun kaynak deposunda base commit'ten
    (verilmezse SON İNDEKSLENEN commit'ten) bu yana değişen dosyaları bulur ve
    "bu değişiklik neyi etkiler?" sorusunu yanıtlar: changed_units (değişen
    dosyalar), chunks_changed, impacted_callers (değişen koda değişiklik kümesi
    DIŞINDAN çağrı yapan metodlar), impacted_subtypes (değişen tiplerin alt
    sınıfları). head verilirse (varsayılan HEAD) iki revizyon ARASI karşılaştırma
    yapılır (revizyon-karşılaştırma modu; HEAD ise çalışma ağacı da dahil).
    Kaynak klasör git deposu değilse zarif hata döner. Dosya-düzeyi diff +
    isim-sezgili graf — kesin statik analiz değildir."""
    return retrieval.analyze_impact(collection, base, head)

@tool
def get_unit_deps(collection: str, unit: str) -> dict:
    """Bir dosyanın (unit) bağımlılık grafiği: uses (bu dosyanın kullandığı
    unit'ler) ve used_by (bu unit'i kullanan dosyalar) — refactor/etki analizi
    için "bu dosyaya kim bağımlı" sorusunun yanıtı. unit tam göreli yol
    ("Core/Utils.pas") ya da unit adı ("Utils") olabilir. Kenarlar indeksleme
    sırasında kaynak dosyaların uses bildirimlerinden çıkarılır."""
    return retrieval.get_unit_deps(collection, unit)

@tool
def get_context_pack(task: str, collections: list[str] | None = None, token_budget: int = 8000,
                      include_relations: bool = True) -> dict:
    """Bir görev/soru için TOKEN BÜTÇELİ hazır bağlam paketi — tek çağrıda: ana
    sembolün TAM kodu, çağıranlar/çağrılanlar, tip hiyerarşisi, unit bağımlılıkları
    ve ikincil eşleşmeler; bütçeye önem sırasıyla doldurulur. Bir ajanın "önce ara,
    sonra tek tek derinleş" döngüsünü tek araca indirger. omitted listesi bütçeye
    sığmayanları gösterir; section id'leriyle get_chunk/get_relations üzerinden
    derinleşilebilir. rerank dahildir (en isabetli sıra)."""
    return retrieval.get_context_pack(task, collections or DEFAULT_COLLECTIONS, token_budget, include_relations)

@tool
def document_unit(collection: str, unit: str, force: bool = False) -> dict:
    """Bir dosyanın (unit, tam göreli yol) teknik dokümantasyonunu Markdown olarak
    üretir: amaç, bağımlılıklar (uses), public API, önemli tipler, notlar. Sonuç
    kalıcı önbelleklenir — aynı unit için tekrar çağrı anında döner (force=True
    yeniden üretir). Yerel Ollama ile üretilir, kod dışarı çıkmaz; ilk üretim
    derin modelle ~30-60 sn sürebilir."""
    return retrieval.document_unit(collection, unit, DEEP_MODEL, force)

@tool
def list_domain_models() -> dict:
    """mcp-config.json'da tanımlı alan-özel (domain) modelleri listeler (örn. sql -> sqlcoder:15b)."""
    return {"domain_models": DOMAIN_MODELS}

@tool
def list_collections() -> dict:
    """Kurulu (aranabilir) indeksleri ve nokta sayılarını listeler. İç sistem
    koleksiyonları (_index_history, _index_profiles) hariç tutulur."""
    return {"collections": retrieval.list_collections()}

if __name__ == "__main__":
    mcp.run(transport="stdio")
