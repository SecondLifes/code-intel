"""Atomik staging+alias indeks nesli modeli (Sıra 27).

Sorun: bugünkü reindex, canlı koleksiyon üzerinde YERİNDE (in-place) diff+upsert
yapıyor — indeksleme sırasında (embedding/upsert batch'leri arasında) arama
yapan biri KISMEN güncellenmiş bir koleksiyon görebilir; süreç ortasında
çökerse koleksiyon ne eski ne yeni, YARIM bir durumda kalır (mevcut _run_index
zaten bunu "yeni/değişen ÖNCE yazılır, silme SONRA yapılır" kuralıyla kısmen
yumuşatıyor — ama tam atomiklik değil).

Çözüm: kullanıcının gördüğü "koleksiyon adı" bir Qdrant ALIAS'ı olur; gerçek
veri versiyonlu bir isimde tutulur (`{ad}__gen1`, `{ad}__gen2`, ...). Yeni
nesil TAMAMEN AYRI bir gerçek koleksiyonda inşa edilir (mevcut nesilden
noktalar KOPYALANIR — yeniden embed edilmez, bkz. seed_from_current), diff
mantığı bu KOPYA üzerinde çalışır; her şey hazır olunca `update_collection_aliases`
ile TEK bir atomik çağrıda takas yapılır — arayan taraf ya TAMAMEN eski ya
TAMAMEN yeni nesli görür, ara durum YOK.

Qdrant alias'ları okuma/yazma noktası işlemlerinde (scroll/search/upsert/
get_collection) GERÇEK koleksiyon adı gibi şeffaf çalışır — canlı Qdrant'a
karşı ampirik olarak doğrulanmıştır (yalnız `create_collection` alias adıyla
ASLA çağrılamaz — 400 döner; `get_collections()` listesi alias'ları DEĞİL
gerçek adları döner, bu yüzden koleksiyon LİSTELEME kodu bu modülden ayrı
tutulur, bkz. `list_generational_collections`).

BİLEREK OPT-IN: mevcut 4 gerçek koleksiyon (Jedi/mORMot2/unidac/
RESTRequest4Delphi) bu modül var olduğu için OTOMATİK OLARAK göçmez —
IndexReq.staged=True açıkça verilmedikçe hiçbir davranış değişmez. Tam
kod-tabanı geneline (get_collections() listeleyen her uç: health, dup-scan,
backup, git-update-all, export...) alias-şeffaf hale getirme dokunuşu, bu
oturumun kapsamı DIŞINDA bırakıldı — gerçek üretim koleksiyonlarına
otomatik/sessiz bir geçiş yapmak yerine, mekanizmanın kendisi atılabilir
fixture koleksiyonlarla uçtan uca kanıtlanıp kullanıcının bilinçli
onayına/seçimine bırakıldı."""
from qdrant_client import models

try:
    from .common import cl
except ImportError:
    from services.common import cl

GEN_SEP = "__gen"

def _gen_name(collection: str, n: int) -> str:
    return f"{collection}{GEN_SEP}{n}"

def is_generational(collection: str) -> bool:
    """`collection` bir alias mı (yani zaten nesil modeline geçmiş mi)?"""
    return any(a.alias_name == collection for a in cl.get_aliases().aliases)

def current_generation(collection: str) -> str | None:
    """`collection` alias'ının şu an işaret ettiği GERÇEK koleksiyon adı — alias
    yoksa None (henüz nesil modeline geçmemiş VEYA hiç yok)."""
    for a in cl.get_aliases().aliases:
        if a.alias_name == collection:
            return a.collection_name
    return None

def _next_gen_number(collection: str) -> int:
    """Var olan TÜM `{collection}__genN` gerçek koleksiyonları tarar, en
    büyüğün bir fazlasını döner — silinmiş ara nesiller varsa bile çakışmaz."""
    prefix = collection + GEN_SEP
    nums = []
    for c in cl.get_collections().collections:
        if c.name.startswith(prefix):
            try:
                nums.append(int(c.name[len(prefix):]))
            except ValueError:
                pass
    return (max(nums) + 1) if nums else 1

def ensure_generational(collection: str) -> str | None:
    """`collection` düz (alias olmayan) bir koleksiyon olarak zaten varsa, onu
    `{collection}__gen1`e taşıyıp (Qdrant'ta rename yok — kopyala+sil, mevcut
    şema `get_collection`den okunur) bir alias kurar. `collection` hiç yoksa
    ya da zaten alias'sa dokunmaz.
    Döner: şu anki GERÇEK koleksiyon adı (alias hedefi) — `collection` hiç
    yoksa None döner (ilk indeksleme senaryosu, çağıran gen1'i sıfırdan kurar)."""
    if is_generational(collection):
        return current_generation(collection)
    if not cl.collection_exists(collection):
        return None
    gen1 = _gen_name(collection, 1)
    info = cl.get_collection(collection)
    cl.create_collection(gen1, vectors_config=info.config.params.vectors,
                          sparse_vectors_config=info.config.params.sparse_vectors)
    _copy_all_points_raw(collection, gen1)
    cl.delete_collection(collection)
    cl.update_collection_aliases(change_aliases_operations=[
        models.CreateAliasOperation(create_alias=models.CreateAlias(
            collection_name=gen1, alias_name=collection))])
    return gen1

def _copy_all_points_raw(src: str, dst: str):
    next_page = None
    while True:
        batch, next_page = cl.scroll(src, limit=1000, offset=next_page, with_payload=True, with_vectors=True)
        if batch:
            cl.upsert(dst, points=[models.PointStruct(id=p.id, vector=p.vector or {}, payload=p.payload) for p in batch])
        if next_page is None:
            break

def start_new_generation(collection: str, vectors_config, sparse_vectors_config, seed: bool = True) -> str:
    """Yeni bir staging nesli oluşturur. `seed=True` ise mevcut nesildeki TÜM
    noktalar (varsa) YENİDEN EMBED EDİLMEDEN kopyalanır — çağıranın diff
    mantığı bu kopya üzerinde çalışıp yalnız gerçekten değişeni işler, tıpkı
    bugünkü yerinde-güncelleme akışındaki gibi (performans karakteri korunur).
    Döner: yeni gerçek koleksiyonun adı (henüz alias'a BAĞLANMADI — takas
    `swap_alias` ile ayrı bir adımda, çağıran hazır olduğuna karar verince)."""
    cur = current_generation(collection)
    n = _next_gen_number(collection)
    new_name = _gen_name(collection, n)
    cl.create_collection(new_name, vectors_config=vectors_config, sparse_vectors_config=sparse_vectors_config)
    if seed and cur and cl.collection_exists(cur):
        _copy_all_points_raw(cur, new_name)
    return new_name

def swap_alias(collection: str, new_real_name: str, keep_previous: int = 1):
    """TEK atomik çağrıda alias'ı yeni nesle çevirir — arayan taraf ya
    TAMAMEN eski ya TAMAMEN yeni nesli görür (bkz. modül docstring'i).
    Takastan SONRA (artık güvenli — kimse eskiye bakmıyor) `keep_previous`
    dışındaki eski nesiller silinir (disk şişmesin)."""
    old = current_generation(collection)
    ops = []
    if old:
        ops.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=collection)))
    ops.append(models.CreateAliasOperation(create_alias=models.CreateAlias(
        collection_name=new_real_name, alias_name=collection)))
    cl.update_collection_aliases(change_aliases_operations=ops)

    prefix = collection + GEN_SEP
    gens = sorted((c.name for c in cl.get_collections().collections if c.name.startswith(prefix)),
                  key=lambda n: int(n[len(prefix):]), reverse=True)
    for stale in gens[keep_previous + 1:]:   # +1: yeni nesil de bu listede, o SAYILMAZ
        if stale != new_real_name:
            cl.delete_collection(stale)

def delete_all_generations(collection: str):
    """`cl.delete_collection(alias)` SESSİZCE HİÇBİR ŞEY YAPMAZ (canlı Qdrant'a
    karşı ampirik olarak doğrulanmıştır — delete_collection, scroll/upsert'in
    aksine alias'ı ÇÖZMEZ) — bu yüzden alias'lı koleksiyonları silen her uç
    (bkz. admin_routes.collection_delete) bunun yerine BU fonksiyonu çağırmalı:
    alias'ın kendisini VE altındaki TÜM `{collection}__genN` gerçek
    koleksiyonlarını siler."""
    try:
        cl.update_collection_aliases(change_aliases_operations=[
            models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=collection))])
    except Exception:
        pass
    prefix = collection + GEN_SEP
    for c in cl.get_collections().collections:
        if c.name.startswith(prefix):
            cl.delete_collection(c.name)

def list_generational_collections() -> dict[str, str]:
    """{kullanıcı-görünür ad: şu anki gerçek nesil adı} — health/liste uçları
    `get_collections()`'ın alias'ları GÖSTERMEDİĞİ (ampirik doğrulanmış Qdrant
    davranışı) durumunu telafi etmek isterse kullanabilir; bu oturumda hiçbir
    mevcut liste ucuna BAĞLANMADI (bkz. modül docstring'i — kapsam dışı)."""
    return {a.alias_name: a.collection_name for a in cl.get_aliases().aliases}
