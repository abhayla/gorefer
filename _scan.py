import ast, pathlib
roots = ["apps", "api", "gorefer"]
hits=[]
for r in roots:
    for p in pathlib.Path(r).rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("filter","exclude"):
                for kw in node.keywords:
                    if kw.arg in ("tenant","tenant_id"):
                        hits.append((str(p).replace("\\","/"), node.lineno))
for h in sorted(hits): print(f"{h[0]}:{h[1]}")
print("TOTAL", len(hits))
