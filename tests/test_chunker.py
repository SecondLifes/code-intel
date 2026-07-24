"""chunker.py için gerçek regresyon testleri — bu oturumda bulunan/düzeltilen
hataların bir daha sessizce geri dönmediğini garanti eder. Harici yol/model/ağ
bağımlılığı yok; hepsi geçici, kendi kendine yeten Pascal parçacıklarıyla çalışır.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from chunker import chunk_file  # noqa: E402


def write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


OVERLOADED_CLASS = """type
  TFoo = class
  public
    /// <summary>Bir kapasite ile olusturur.</summary>
    constructor Create(ACapacity: Integer); overload;
    /// <summary>Sahiplik bayragiyla olusturur.</summary>
    constructor Create(AOwnsValues: Boolean; ACapacity: Integer = 0); overload;
  end;
"""


def test_line_shift_does_not_change_chunk_id(tmp_path):
    """KRİTİK regresyon: bir chunk'ın ÜSTÜNE satır eklemek, içeriği aynı kalan
    chunk'ların ID'sini DEĞİŞTİRMEMELİ (satır no ID'ye katılmıyor olmalı)."""
    p = write(tmp_path, "idtest.pas", OVERLOADED_CLASS)
    before = {ch["name"] + str(i): ch["id"] for i, ch in enumerate(chunk_file(p, "test"))}

    shifted = "// alakasiz bir yorum satiri\n" + OVERLOADED_CLASS
    write(tmp_path, "idtest.pas", shifted)
    after = {ch["name"] + str(i): ch["id"] for i, ch in enumerate(chunk_file(p, "test"))}

    assert set(before.values()) == set(after.values()), \
        "satır kayması chunk ID'lerini değiştirdi — diffleme/önbellek sistemini bozar"


def test_overloaded_methods_get_distinct_ids(tmp_path):
    """Aynı isimli (overload) method bildirimleri farklı ID almalı — imzaları
    farklı olduğu sürece full_text önek karşılaştırması bunu ayırt etmeli."""
    p = write(tmp_path, "overload.pas", OVERLOADED_CLASS)
    chunks = [ch for ch in chunk_file(p, "test") if ch["kind"] == "decl"]
    assert len(chunks) == 2
    assert chunks[0]["id"] != chunks[1]["id"]
    assert chunks[0]["name"] == chunks[1]["name"] == "Create"


def test_same_basename_different_folder_gets_distinct_unit_and_id(tmp_path):
    """Aynı dosya adı, farklı klasör → farklı 'unit' etiketi VE farklı ID
    (path.name yerine kök-göreli yol kullanılmalı)."""
    core = tmp_path / "Core"; core.mkdir()
    providers = tmp_path / "Providers"; providers.mkdir()
    write(core, "Utils.pas", "type\n  TCoreUtils = class\n    procedure DoCoreThing;\n  end;\n")
    write(providers, "Utils.pas", "type\n  TProviderUtils = class\n    procedure DoProviderThing;\n  end;\n")

    core_chunks = list(chunk_file(core / "Utils.pas", "test", "Core/Utils.pas"))
    prov_chunks = list(chunk_file(providers / "Utils.pas", "test", "Providers/Utils.pas"))

    assert core_chunks[0]["unit"] == "Core/Utils.pas"
    assert prov_chunks[0]["unit"] == "Providers/Utils.pas"
    assert core_chunks[0]["id"] != prov_chunks[0]["id"]


def test_doc_comment_extracted_and_cleaned(tmp_path):
    """/// <summary>...</summary> hem 'doc' alanına düz metin olarak çıkarılmalı
    hem de chunk metnine (embedding/gösterim için) dahil edilmeli."""
    p = write(tmp_path, "doctest.pas", OVERLOADED_CLASS)
    chunks = [ch for ch in chunk_file(p, "test") if ch["kind"] == "decl"]
    docs = {ch["doc"] for ch in chunks}
    assert "Bir kapasite ile olusturur." in docs
    assert "Sahiplik bayragiyla olusturur." in docs
    for ch in chunks:
        assert "<summary>" not in ch["doc"] and "</summary>" not in ch["doc"]
        assert ch["doc"] in ch["code"]   # doc, chunk metninin başına eklenmiş olmalı


def test_content_change_changes_hash_but_not_necessarily_id(tmp_path):
    """İçerik gerçekten değişirse hash değişmeli (diffleme bunu 'changed' görsün)."""
    p = write(tmp_path, "x.pas", OVERLOADED_CLASS)
    before = {ch["id"]: ch["hash"] for ch in chunk_file(p, "test")}
    changed = OVERLOADED_CLASS.replace("Bir kapasite ile olusturur.", "Degistirilmis bir aciklama metni.")
    write(tmp_path, "x.pas", changed)
    after = {ch["id"]: ch["hash"] for ch in chunk_file(p, "test")}
    assert before != after   # en az bir chunk'ın hash'i değişmiş olmalı


def test_noise_filter_drops_tiny_declarations_without_doc(tmp_path):
    """Doc yorumu olmayan çok kısa bildirimler (gürültü) atlanmalı."""
    p = write(tmp_path, "tiny.pas", "type\n  TA = class\n    destructor Destroy; override;\n  end;\n")
    decls = [ch for ch in chunk_file(p, "test") if ch["kind"] == "decl"]
    assert decls == []   # "destructor Destroy; override;" tek başına 40 karakterden kısa


# ---------------- Chunker v2 (Sıra 5) ----------------
FULL_UNIT = """unit MyUnit;

interface

uses SysUtils, Classes, Generics.Collections;

function Foo: Integer;

implementation

uses Windows {yorum}, Messages, Vcl.Forms in '..\\Vcl.Forms.pas';

function Foo: Integer;
begin
  Result := 1;
end;

end.
"""


def test_v2_unithead_extracts_uses(tmp_path):
    """`unit X;` başlıklı dosyalar kind=unithead chunk'ı üretmeli; uses listesi
    her iki bölümden, yorumlar ve `in '...'` ekleri ayıklanmış halde gelmeli."""
    p = write(tmp_path, "MyUnit.pas", FULL_UNIT)
    heads = [ch for ch in chunk_file(p, "test") if ch["kind"] == "unithead"]
    assert len(heads) == 1
    assert heads[0]["name"] == "MyUnit"
    assert heads[0]["uses"] == ["SysUtils", "Classes", "Generics.Collections", "Windows", "Messages", "Vcl.Forms"]


def test_v2_headerless_file_has_no_unithead(tmp_path):
    """Başlıksız parçalar (include/test kırpıntıları) unithead ÜRETMEMELİ."""
    p = write(tmp_path, "frag.pas", OVERLOADED_CLASS)
    assert not [ch for ch in chunk_file(p, "test") if ch["kind"] == "unithead"]


def test_v2_huge_method_included_with_flag(tmp_path):
    """>400 satırlık metodlar v1'de TAMAMEN atlanıyordu — v2'de kırpılmış kod +
    huge=true bayrağıyla indekslenmeli (tam kod diskten-okuma yoluyla gelir)."""
    body = "function Big: Integer;\nbegin\n" + "  Result := 1;\n" * 450 + "end;\n"
    p = write(tmp_path, "big.pas", "unit Big;\ninterface\nfunction Big: Integer;\nimplementation\n" + body + "end.\n")
    methods = [ch for ch in chunk_file(p, "test") if ch["kind"] == "method"]
    assert methods and methods[0].get("huge") is True
    assert methods[0]["code"].count("\n") <= 402
    assert methods[0]["line_end"] > 400   # gerçek satır aralığı korunur


def test_v2_id_is_repo_scoped(tmp_path):
    """Aynı dosya farklı lib ile chunk'lanınca ID'ler FARKLI olmalı — merge'de
    kütüphaneler arası sessiz ID çakışmasını bitiren repo-kimlikli ID."""
    p = write(tmp_path, "MyUnit.pas", FULL_UNIT)
    a = {ch["name"] + ch["kind"]: ch["id"] for ch in chunk_file(p, "libA")}
    b = {ch["name"] + ch["kind"]: ch["id"] for ch in chunk_file(p, "libB")}
    assert a and all(a[k] != b[k] for k in a)
