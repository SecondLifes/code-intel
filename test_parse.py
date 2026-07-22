from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser
lang = get_language("pascal"); parser = get_parser("pascal")
src_path = r"E:\system\dev\son ayrım\01-Component\2026.6.6\UniDAC 10.3.0\Source\Uni.pas"
code = open(src_path, "rb").read()
tree = parser.parse(code)
print("PARSE OK | hata dugumu:", tree.root_node.has_error, "| boyut:", len(code), "bayt")
q = Query(lang, "(declProc) @decl\n(defProc) @impl\n(declType) @type")
caps = QueryCursor(q).captures(tree.root_node)
print("Yakalanan:", {k: len(v) for k, v in caps.items()})
for node in caps.get("impl", [])[:3]:
    line = code[node.start_byte:node.start_byte+90].decode("utf-8","replace").split("\n")[0]
    print(f"  L{node.start_point[0]+1}-{node.end_point[0]+1}: {line.strip()}")
