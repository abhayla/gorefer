import pathlib, sys
def apply(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        n = s.count(a)
        if n != 1:
            print(f"FAIL {path}: {n} matches for:\n{a}")
            sys.exit(1)
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8")
    print(f"ok {path} ({len(pairs)})")
