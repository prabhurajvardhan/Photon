# Photon (`v0-beta`) — by Nanoware AI

**Massless, local-first code intelligence.** An approximately **49 MB quantized ONNX (`48.62 MB` INT4)** patch engine for Python and TypeScript compiler/runtime errors, paired with a `<4 ms` **Symbol-Dependency AST Slicer** and zero-config **MCP server**.

## Verified `v0-beta` Benchmarks
Measured on Kaggle `x86_64` CPU (4 threads, KV-Cached INT4 ONNX) and NVIDIA T4 GPU:

| Metric | Measured Result | Hardware / Conditions |
| :--- | :--- | :--- |
| **ONNX Model Footprint** | **48.62 MB** | Self-contained INT4 (`block_size=32`) |
| **AST Slicer Compression** | **3,444 -> 23 tokens (`3.77 ms`)** | 600-line Python file (`x86_64` CPU) |
| **KV-Cached CPU Decode (`<=281` tokens)** | **60.0 – 79.0 tok/s** | `2.50 – 3.59 / 4` speculative hit rate (`x86_64` CPU) |
| **KV-Cached CPU Decode (`1,037` tokens)** | **16.4 tok/s** | `1.37 / 4` speculative hit rate (`x86_64` CPU) |
| **GPU Decode Throughput** | **727.4 tok/s** | NVIDIA T4 FP16 (`3.60 / 4` speculative hit rate) |

## Quickstart
```bash
pip install --pre nanoware-photon
photon fix app.py --line 42 --err "NameError: name 'requests' is not defined" --apply
```

## MCP Configuration (Cursor, Claude Code, Windsurf, Cline)
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

## Nanoware Private Patch Intelligence (B2B Custom Adaptation)
- **Pilot Deployment (`₹9,999` one-time introductory offer):** Custom adaptation of Photon on **1 approved internal repository or SDK**, reproducible benchmark report, and local `~49 MB` ONNX deployment with strict dataset isolation and post-training deletion guarantees.
- **Business & Enterprise Deployments:** Multi-repository adaptation, IDE workflow integration, and ongoing maintenance agreements.

## Licensing
- **CLI, AST Slicer & MCP Interface:** Apache-2.0 (`LICENSE`).
- **Model Weights:** `WEIGHTS_LICENSE.md`.
