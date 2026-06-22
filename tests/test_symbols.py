from logos_copilot.symbols import extract_symbols, lookup_symbol


def test_lookup_empty_key_returns_empty():
    # empty / whitespace / slash-only must NOT match everything (conn unused before the guard)
    assert lookup_symbol(None, "") == []
    assert lookup_symbol(None, "   ") == []
    assert lookup_symbol(None, "/") == []


def test_rust_symbols():
    code = "pub fn upload(data: &[u8]) -> Cid {\n  todo!()\n}\nstruct Node;\n"
    syms = {s["name"]: s for s in extract_symbols("src/lib.rs", code)}
    assert "upload" in syms and syms["upload"]["kind"] == "fn"
    assert "pub fn upload" in syms["upload"]["signature"]
    assert "Node" in syms and syms["Node"]["kind"] == "struct"


def test_typescript_symbols():
    code = ("export class Codex {}\n"
            "export function createNode(opts) {}\n"
            "export const upload = async (x) => x\n")
    syms = {s["name"]: s["kind"] for s in extract_symbols("src/api.ts", code)}
    assert syms.get("Codex") == "class"
    assert syms.get("createNode") == "fn"
    assert syms.get("upload") == "fn"


def test_python_symbols():
    syms = {s["name"]: s["kind"] for s in extract_symbols("m.py", "class A:\n    def f(self): pass\n")}
    assert syms.get("A") == "class" and syms.get("f") == "fn"


def test_openapi_endpoints():
    spec = 'paths:\n  "/data":\n    post:\n      x: y\n  "/data/{cid}":\n    get: {}\n'
    eps = [s for s in extract_symbols("api/openapi.yaml", spec) if s["kind"] == "endpoint"]
    names = {s["name"] for s in eps}
    assert "/data" in names and "/data/{cid}" in names


def test_non_code_returns_empty():
    assert extract_symbols("README.md", "# hi\nsome text") == []
