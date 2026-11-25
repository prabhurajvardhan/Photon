# Photon (v0-beta) — by Nanoware AI

Local-first Python & TypeScript compiler patch engine (~48.6 MB INT4 ONNX) with a <4 ms Symbol-Dependency AST Slicer and MCP server.

## 1. Setup
```bash
pip install --pre nanoware-photon
```

## 2. Quick Demo
```bash
photon fix app.py --line 2 --err "NameError: name 'requests' is not defined" --apply
```

## 3. MCP Setup (Cursor, Claude Code, Windsurf, Cline)
Add to `.cursor/mcp.json`, `.mcp.json`, or `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "photon": {
      "command": "photon",
      "args": ["mcp"]
    }
  }
}
```

## 3a. Authenticated remote MCP worker
The package also provides a pure-Python Streamable HTTP worker. It contains no
browser UI; route browser GET traffic to the separately deployed Photon Portal
and route MCP POST traffic to this worker at `/photon`.

```bash
PHOTON_OAUTH_JWT_SECRET=replace-me \
NANOS_API_BASE_URL=https://nanowareai.in \
photon serve-http --host 0.0.0.0 --port 8080
```

Unauthenticated MCP requests receive a `401` response with the OAuth protected
resource metadata URL. Authenticated `fix_code_error` calls meter input at
`1 Nano/token` and output at `3 Nanos/token` through the Nanoware AI ledger.

## 4. Verified Benchmarks (v0-beta)
- Binary Size: 48.62 MB INT4 ONNX
- AST Slicer: 3,444 -> 23 tokens in 3.77 ms (x86_64 CPU)
- KV-Cached CPU Decode (<=281 tokens): 60.0 - 79.0 tok/s (2.50 - 3.59/4 hit rate)
- GPU Decode (T4 FP16): 727.4 tok/s (3.60/4 hit rate)

Run `python bench.py` to reproduce locally.

## 5. Private Patch Intelligence (B2B)
- Pilot Deployment (INR 9,999 one-time): Custom adaptation on 1 approved internal repo/SDK + benchmark report + local deployment.
