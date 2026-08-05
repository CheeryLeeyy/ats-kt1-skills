#!/usr/bin/env python3
"""Create a compact, durable summary before disposable run outputs are removed."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path
from typing import Any


def parse_metric_yaml(path: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.fullmatch(r"(ap30|ap_50|ap_70):\s*([-+0-9.eE]+)", line.strip())
        if match:
            result[match.group(1)] = float(match.group(2))
        if len(result) == 3:
            break
    return result


def npy_info(path: Path) -> dict[str, Any]:
    try:
        import numpy as np

        array = np.load(path, mmap_mode="r", allow_pickle=False)
        return {"shape": list(array.shape), "dtype": str(array.dtype), "size": int(array.size)}
    except Exception as exc:
        return {"error": str(exc)}


def png_info(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", header[16:24])
        return {"width": width, "height": height, "size_bytes": path.stat().st_size}
    return {"error": "not a PNG"}


def text_sample(path: Path, limit: int = 12000) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        sample = text
        truncated = False
    else:
        half = limit // 2
        sample = text[:half] + "\n...[中间内容省略]...\n" + text[-half:]
        truncated = True
    return {"size_bytes": path.stat().st_size, "truncated": truncated, "sample": sample}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    output_dir = run_dir / "output"
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    data: dict[str, Any] = {
        "package": run["package"],
        "image": run["image"],
        "status": run["status"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "load": run["load"],
        "run": run["run"],
        "docker_command_shell": run["docker_command_shell"],
        "params_json": run["params_json"],
        "forced_runtime": run["forced_runtime"],
        "runtime_env": run.get("runtime_env", {}),
        "input_inventory": run["input_inventory"],
        "output_inventory": run["output_inventory"],
    }
    result_json = output_dir / "result.json"
    if result_json.exists():
        data["result_json"] = json.loads(result_json.read_text(encoding="utf-8"))
    json_outputs: dict[str, Any] = {}
    for path in sorted(output_dir.rglob("*.json")):
        if path == result_json or path.stat().st_size > 5 * 1024 * 1024:
            continue
        relative = str(path.relative_to(output_dir))
        try:
            json_outputs[relative] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            json_outputs[relative] = {"error": str(exc), "size_bytes": path.stat().st_size}
        if len(json_outputs) >= 200:
            break
    if json_outputs:
        data["json_outputs"] = json_outputs
    text_outputs: dict[str, Any] = {}
    for pattern in ("*.txt", "*.csv", "*.log"):
        for path in sorted(output_dir.rglob(pattern)):
            relative = str(path.relative_to(output_dir))
            text_outputs[relative] = text_sample(path)
            if len(text_outputs) >= 100:
                break
        if len(text_outputs) >= 100:
            break
    if text_outputs:
        data["text_outputs"] = text_outputs
    metric_files = []
    before_text = (output_dir / "_model_dir_before.txt").read_text(errors="replace") if (output_dir / "_model_dir_before.txt").exists() else ""
    for path in sorted(output_dir.glob("eval*.yaml")):
        metric_files.append(
            {
                "name": path.name,
                "metrics": parse_metric_yaml(path),
                "existed_in_model_dir_before_run": path.name in before_text,
            }
        )
    if metric_files:
        data["metric_files"] = metric_files
    npy_dir = output_dir / "npy"
    if npy_dir.is_dir():
        data["npy_samples"] = {
            name: npy_info(npy_dir / name)
            for name in ("0000_gt.npy", "0000_pcd.npy", "0000_pred.npy")
            if (npy_dir / name).exists()
        }
    pngs = sorted(output_dir.glob("vis*/**/*.png"))
    if pngs:
        data["visualization_sample"] = {"path": str(pngs[0].relative_to(output_dir)), **png_info(pngs[0])}
        data["visualization_png_count"] = len(pngs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
