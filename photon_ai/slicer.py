import ast, re

def slice_huge_file_surgical(file_path: str, error_line: int) -> tuple[str, str]:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    lines = source.splitlines()
    if file_path.endswith(".py"):
        try:
            tree = ast.parse(source)
            target_node, top_defs = None, {}
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        name = alias.asname or next(iter(alias.name.split(".")), "")
                        if name:
                            top_defs[name] = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    top_defs[node.name] = lines[node.lineno - 1]
                    if node.lineno <= error_line <= node.end_lineno:
                        target_node = node
            if target_node is not None:
                broken_fn = "\n".join(lines[target_node.lineno - 1 : target_node.end_lineno])
                used_names = {n.id for n in ast.walk(target_node) if isinstance(n, ast.Name)}
                headers, seen = [], set()
                for name in used_names:
                    if name in top_defs and name != target_node.name and top_defs[name] not in seen:
                        headers.append(top_defs[name]); seen.add(top_defs[name])
                hdr = "\n".join(headers)
                return (f"{hdr}\n\n{broken_fn}".strip() if hdr else broken_fn), broken_fn
        except SyntaxError:
            pass
    broken_fn = "\n".join(lines[max(0, error_line - 15) : min(len(lines), error_line + 15)])
    words = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", broken_fn))
    hdrs = [l for l in lines if l.strip().startswith(("import ", "interface ", "type ", "const ", "enum ")) and any(w in l for w in words)]
    hdr = "\n".join(hdrs[:15])
    return (f"{hdr}\n\n{broken_fn}".strip() if hdr else broken_fn), broken_fn
