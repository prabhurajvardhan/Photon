import sys, json, argparse
from .slicer import slice_huge_file_surgical
from .engine import TinyCodeEngine

def run_mcp(engine: TinyCodeEngine):
    for line in sys.stdin:
        req = json.loads(line)
        m = req.get("method")
        if m == "initialize":
            resp = {"jsonrpc": "2.0", "id": req["id"], "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "photon", "version": "0.1.0-beta"}, "capabilities": {"tools": {}}}}
        elif m == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req["id"], "result": {"tools": [{"name": "fix_compiler_error", "description": "Patches Python/TypeScript compiler errors locally using ~49MB INT4 model + AST slicer.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "error_line": {"type": "integer"}, "error_msg": {"type": "string"}}, "required": ["file_path", "error_line", "error_msg"]}}]}}
        elif m == "tools/call":
            a = req["params"]["arguments"]
            ctx, bfn = slice_huge_file_surgical(a["file_path"], a["error_line"])
            patch = engine.generate_patch("py" if a["file_path"].endswith(".py") else "ts", a["error_msg"], ctx, bfn)
            resp = {"jsonrpc": "2.0", "id": req["id"], "result": {"content": [{"type": "text", "text": patch}]}}
        else:
            continue
        sys.stdout.write(json.dumps(resp) + "\n"); sys.stdout.flush()

def main():
    p = argparse.ArgumentParser(prog="photon")
    sub = p.add_subparsers(dest="cmd", required=True)
    fp = sub.add_parser("fix")
    fp.add_argument("file"); fp.add_argument("--line", type=int, required=True); fp.add_argument("--err", required=True); fp.add_argument("--apply", action="store_true")
    sub.add_parser("mcp")
    args = p.parse_args()
    eng = TinyCodeEngine()
    if args.cmd == "mcp":
        run_mcp(eng)
    else:
        ctx, bfn = slice_huge_file_surgical(args.file, args.line)
        fix = eng.generate_patch("py" if args.file.endswith(".py") else "ts", args.err, ctx, bfn)
        print(f"--- Patch ---\n{fix}\n-------------")
        if args.apply:
            txt = open(args.file).read()
            if bfn in txt:
                open(args.file, "w").write(txt.replace(bfn, fix, 1))
                print(f"Applied to {args.file}")

if __name__ == "__main__":
    main()
