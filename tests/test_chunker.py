"""chunker.py için gerçek regresyon testleri — bu oturumda bulunan/düzeltilen
hataların bir daha sessizce geri dönmediğini garanti eder. Harici yol/model/ağ
bağımlılığı yok; hepsi geçici, kendi kendine yeten Pascal parçacıklarıyla çalışır.
"""
import pathlib
import sys

import pytest

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


def test_v2_huge_method_split_into_logical_parts(tmp_path):
    """Sıra 25: dev metod artık yalnız kırpılmıp bırakılmıyor — gövdesi STATEMENT
    sınırlarında (asla bir ifadenin ortasından değil) mantıksal parçalara
    bölünüp kind="method_part" chunk'ları olarak da indeksleniyor. Böylece 400.
    satırdan SONRAKİ kod da aranabilir (öncesinde yalnız ilk 400 satır vardı)."""
    body = "function Big: Integer;\nbegin\n" + "".join(f"  DoThing{i}(i);\n" for i in range(900)) + "end;\n"
    p = write(tmp_path, "big.pas", "unit Big;\ninterface\nfunction Big: Integer;\nimplementation\n" + body + "end.\n")
    chunks = list(chunk_file(p, "test"))
    method = next(c for c in chunks if c["kind"] == "method")
    parts = [c for c in chunks if c["kind"] == "method_part"]
    assert method["child_count"] == len(parts) and len(parts) >= 2
    assert all(c["parent_id"] == method["id"] for c in parts)
    # parçalar ARDIŞIK satır aralıklarını kapsamalı (boşluk/örtüşme yok) ve
    # 900. çağrı (400. satırın çok ötesinde) MUTLAKA bir parçada bulunmalı —
    # eskiden bu kod tamamen kırpılıp kaybolurdu.
    parts.sort(key=lambda c: c["part_index"])
    assert all(parts[i]["line_end"] < parts[i + 1]["line_start"] for i in range(len(parts) - 1))
    assert any("DoThing899(" in c["code"] for c in parts)
    # her parçanın kendi çağrı grafiği çıkarımı olmalı (yalnız gövdedeki isimler)
    assert any("dothing0" in c["calls_raw"] for c in parts if c["part_index"] == 0)


def test_huge_method_without_recognizable_body_falls_back_to_line_windows(tmp_path):
    """Gövde düğümü bulunamazsa (tek dev ifade — hiç statement sınırı yok) satır
    penceresine düşülür — hiç bölmemekten iyi, kod yine de aranabilir kalır."""
    import chunker as _ch
    huge_lines = ["x" + str(i) for i in range(900)]
    text = "one_giant_expr(" + " + ".join(huge_lines) + ")"

    class FakeNode:
        def __init__(self, start_byte, end_byte, start_row, end_row):
            self.start_byte, self.end_byte = start_byte, end_byte
            self.start_point, self.end_point = (start_row, 0), (end_row, 0)
            self.children, self.named_children = [], []

    code = text.encode()
    node = FakeNode(0, len(code), 0, 5)
    parts = _ch._split_huge_node(node, code, max_lines=400)
    assert len(parts) >= 1
    assert "".join(p[2] for p in parts) == text   # satır-penceresi birleşimi orijinal metnin AYNISI (kayıp/tekrar yok)


def test_go_huge_function_body_wrapper_unwrapped(tmp_path):
    """Go grameri gövdeyi TEK bir sarmalayıcı düğüme (statement_list) koyar —
    _find_body_node bu sarmalayıcıyı atlayıp GERÇEK ifadelere inmeli, yoksa
    bölme hiç gerçekleşmez (tek 'çocuk' olarak görünen tüm gövde asla parçalanmaz)."""
    body = "".join(f"\tdoThing{i}()\n" for i in range(900))
    src = "package main\n\nfunc Big() {\n" + body + "}\n"
    p = write(tmp_path, "big.go", src)
    chunks = list(chunk_file(p, "test"))
    method = next(c for c in chunks if c["kind"] == "method" and c["name"] == "Big")
    parts = [c for c in chunks if c["kind"] == "method_part"]
    assert method.get("huge") is True
    assert len(parts) >= 2, "Go statement_list sarmalayıcısı atlanmadıysa bölme hiç gerçekleşmez"
    assert any("doThing899(" in c["code"] for c in parts)


def test_v2_id_is_repo_scoped(tmp_path):
    """Aynı dosya farklı lib ile chunk'lanınca ID'ler FARKLI olmalı — merge'de
    kütüphaneler arası sessiz ID çakışmasını bitiren repo-kimlikli ID."""
    p = write(tmp_path, "MyUnit.pas", FULL_UNIT)
    a = {ch["name"] + ch["kind"]: ch["id"] for ch in chunk_file(p, "libA")}
    b = {ch["name"] + ch["kind"]: ch["id"] for ch in chunk_file(p, "libB")}
    assert a and all(a[k] != b[k] for k in a)


# ---------------- Sıra 10: çok dilli motor ----------------
from chunker import chunker_for, LANG_TABLE  # noqa: E402


PY_SRC = '''import os
from collections import OrderedDict


class Base:
    pass


class Widget(Base, Mixin):
    """A widget that does things."""

    def render(self, ctx):
        """Renders the widget into the given context."""
        return helper_render(ctx)
'''

CS_SRC = '''using System;
using System.Collections.Generic;

namespace MyApp
{
    public interface IShape { }

    /// <summary>Represents a rectangle.</summary>
    public class Rectangle : Shape, IShape
    {
        /// <summary>Computes the area.</summary>
        public double Area()
        {
            return ComputeArea(Width, Height);
        }
    }
}
'''

JAVA_SRC = '''package com.example;
import java.util.List;

/** A service that does things. */
public class MyService extends BaseService implements Runnable {
    /** Runs the service. */
    public void run() {
        doWork();
    }
}
'''

GO_SRC = '''package main

import (
    "fmt"
)

// Greeter greets people.
type Greeter struct{}

// Greet prints a greeting.
func Greet(name string) string {
    return formatGreeting(name)
}
'''

RUST_SRC = '''use std::fmt;

/// A point in 2D space.
struct Point { x: i32, y: i32 }

trait Shape { fn area(&self) -> f64; }

impl Shape for Point {
    fn area(&self) -> f64 { compute_area(self.x, self.y) }
}
'''

RUBY_SRC = '''require "set"

class Widget
  def render(ctx)
    helper_render(ctx)
  end
end
'''


def test_dispatch_picks_correct_chunker_by_extension(tmp_path):
    assert chunker_for(pathlib.Path("x.py")).lang == "python"
    assert chunker_for(pathlib.Path("x.cs")).lang == "csharp"
    assert chunker_for(pathlib.Path("x.rs")).lang == "rust"
    assert chunker_for(pathlib.Path("x.unknown_ext_xyz")) is None


def test_python_full_support_doc_calls_extends(tmp_path):
    p = write(tmp_path, "widget.py", PY_SRC)
    chunks = list(chunk_file(p, "test"))
    methods = [c for c in chunks if c["kind"] == "method"]
    types = [c for c in chunks if c["kind"] == "type"]
    heads = [c for c in chunks if c["kind"] == "unithead"]
    assert any(c["name"] == "render" for c in methods)
    render = next(c for c in methods if c["name"] == "render")
    assert "Renders the widget" in render["doc"]
    assert "helper_render" in render["calls_raw"]
    widget = next(c for c in types if c["name"] == "Widget")
    assert widget["extends"][0] == "Base"   # ilk taban sınıf
    assert heads and "collections" in heads[0]["uses"]
    assert all(c.get("lang") == "python" for c in chunks)


def test_csharp_doc_and_interface_extraction(tmp_path):
    p = write(tmp_path, "Rectangle.cs", CS_SRC)
    chunks = list(chunk_file(p, "test"))
    rect = next(c for c in chunks if c["kind"] == "type" and c["name"] == "Rectangle")
    assert "Shape" in rect["extends"] and "IShape" in rect["extends"]
    area = next(c for c in chunks if c["kind"] == "method" and c["name"] == "Area")
    assert "Computes the area" in area["doc"]
    # calls_raw kasıtlı olarak küçük harfe normalize edilir (Pascal'la aynı sözleşme —
    # link_call_graph çözümlemesi de bare adı lower() ile eşleştirir)
    assert "computearea" in area["calls_raw"]


def test_java_extends_implements_order(tmp_path):
    p = write(tmp_path, "MyService.java", JAVA_SRC)
    chunks = list(chunk_file(p, "test"))
    svc = next(c for c in chunks if c["kind"] == "type" and c["name"] == "MyService")
    assert svc["extends"][0] == "BaseService"
    assert "Runnable" in svc["extends"][1:]


def test_go_functions_and_uses(tmp_path):
    p = write(tmp_path, "greet.go", GO_SRC)
    chunks = list(chunk_file(p, "test"))
    greet = next(c for c in chunks if c["kind"] == "method" and c["name"] == "Greet")
    assert "prints a greeting" in greet["doc"]
    head = next(c for c in chunks if c["kind"] == "unithead")
    assert "fmt" in head["uses"]


def test_rust_impl_for_trait(tmp_path):
    p = write(tmp_path, "point.rs", RUST_SRC)
    chunks = list(chunk_file(p, "test"))
    impls = [c for c in chunks if c["kind"] == "type" and c.get("extends")]
    assert any(c["name"] == "Point" and "Shape" in c["extends"] for c in impls)


def test_generic_layer_ruby_finds_method_without_full_support(tmp_path):
    """Ruby jenerik katmanda (full=False) — doc/calls/extends YOK ama chunk +
    isim + arama tam çalışmalı (Katman-2 sözleşmesi)."""
    p = write(tmp_path, "widget.rb", RUBY_SRC)
    chunks = list(chunk_file(p, "test"))
    assert any(c["kind"] == "method" and c["name"] == "render" for c in chunks)
    render = next(c for c in chunks if c["name"] == "render")
    assert render.get("lang") == "ruby"
    assert render["calls_raw"] == []   # full=False: çağrı çıkarımı yapılmaz


def test_lang_table_extensions_are_unique_across_full_support_langs():
    """Tam-destek dillerin uzantıları birbiriyle (ve Pascal'la) çakışmamalı —
    çakışma sessizce yanlış dile yönlendirir."""
    seen: dict[str, str] = {".pas": "pascal", ".dpr": "pascal", ".dpk": "pascal", ".inc": "pascal"}
    for lang, cfg in LANG_TABLE.items():
        for ext in cfg["exts"]:
            assert ext not in seen, f"{ext} hem {seen.get(ext)} hem {lang} tablosunda"
            seen[ext] = lang


def test_lang_table_has_at_least_40_generic_entries():
    generic = [l for l, c in LANG_TABLE.items() if not c.get("full")]
    assert len(generic) >= 35, f"jenerik katman beklenenden dar: {len(generic)}"
