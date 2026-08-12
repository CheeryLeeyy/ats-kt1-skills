#!/usr/bin/env python3
"""Load one submitted image, run one isolated test, and capture evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_stream(command: list[str], log_path: Path) -> tuple[int, float]:
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {shlex.join(command)}\n")
        log.flush()
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
        return_code = process.wait()
        elapsed = time.monotonic() - started
        log.write(f"\n[exit_code={return_code} duration_seconds={elapsed:.3f}]\n")
    return return_code, elapsed


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path, hash_files: bool) -> dict[str, Any]:
    by_extension: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        stat = path.stat()
        relative = str(path.relative_to(root))
        extension = path.suffix.lower() or "[none]"
        by_extension[extension]["count"] += 1
        by_extension[extension]["bytes"] += stat.st_size
        total_bytes += stat.st_size
        record: dict[str, Any] = {
            "path": relative,
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        }
        if hash_files:
            record["sha256"] = sha256(path)
        files.append(record)
    return {
        "root": str(root.resolve()),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "by_extension": dict(sorted(by_extension.items())),
        "files": files,
    }


def load_params(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("params.json must contain an object")
    forbidden = {"volume", "volumes", "mount", "mounts"} & data.keys()
    if forbidden:
        raise ValueError(f"params.json may not define mounts: {sorted(forbidden)}")
    return data


def image_exists(image: str) -> bool:
    return subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def image_inspect(image: str) -> Any:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algorithm-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--input", default="input", help="path relative to algorithm dir, or absolute")
    parser.add_argument("--case", default="default", help="short case label")
    parser.add_argument("--force-gpus", help="verified GPU argument when params.json is incomplete")
    parser.add_argument("--force-shm-size", help="verified shm-size when params.json is incomplete")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="verified container environment override; may be repeated",
    )
    parser.add_argument(
        "--container-command-json",
        help=(
            "JSON array used to override the image CMD for a bounded validation run; "
            "the complete override is retained in run.json"
        ),
    )
    parser.add_argument("--skip-load", action="store_true")
    args = parser.parse_args()

    algorithm_dir = args.algorithm_dir.resolve()
    package = algorithm_dir.name
    if not package.startswith("algo1-4-j-"):
        raise ValueError(f"unexpected algorithm directory name: {package}")
    image = f"{package}:v1"
    archive = algorithm_dir / f"{package}.tar"
    if not archive.is_file():
        raise FileNotFoundError(archive)
    input_arg = Path(args.input)
    input_dir = input_arg.resolve() if input_arg.is_absolute() else (algorithm_dir / input_arg).resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(input_dir)
    case_dir = args.work_dir.resolve() / package / args.case
    output_dir = case_dir / "output"
    if case_dir.exists() and any(case_dir.iterdir()):
        raise FileExistsError(f"refusing to reuse non-empty evidence directory: {case_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    params_path = algorithm_dir / "params.json"
    params = load_params(params_path)
    runtime_env: dict[str, str] = {}
    for item in args.env:
        if "=" not in item:
            raise ValueError(f"--env must be NAME=VALUE: {item!r}")
        name, value = item.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"invalid environment variable name: {name!r}")
        runtime_env[name] = value
    container_command: list[str] = []
    if args.container_command_json:
        parsed_command = json.loads(args.container_command_json)
        if not isinstance(parsed_command, list) or not parsed_command:
            raise ValueError("--container-command-json must be a non-empty JSON array")
        if not all(isinstance(item, str) and item for item in parsed_command):
            raise ValueError("every container command item must be a non-empty string")
        container_command = parsed_command
    gpu_value = args.force_gpus if args.force_gpus is not None else params.get("gpus")
    shm_value = args.force_shm_size if args.force_shm_size is not None else params.get("shm-size")
    existed_before = image_exists(image)
    input_inventory = inventory(input_dir, hash_files=False)
    record: dict[str, Any] = {
        "package": package,
        "image": image,
        "archive": str(archive),
        "input": str(input_dir),
        "output": str(output_dir),
        "case": args.case,
        "params_json": params,
        "forced_runtime": {"gpus": args.force_gpus, "shm-size": args.force_shm_size},
        "runtime_env": runtime_env,
        "container_command_override": container_command,
        "image_existed_before": existed_before,
        "started_at": utc_now(),
        "input_inventory": {key: value for key, value in input_inventory.items() if key != "files"},
    }
    (case_dir / "input_inventory.json").write_text(
        json.dumps(input_inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    load_code = 0
    load_duration = 0.0
    if not args.skip_load and not existed_before:
        load_code, load_duration = run_stream(
            ["docker", "load", "--input", str(archive)], case_dir / "docker-load.log"
        )
    else:
        (case_dir / "docker-load.log").write_text(
            f"load skipped; image_existed_before={existed_before} skip_load={args.skip_load}\n",
            encoding="utf-8",
        )
    record["load"] = {"exit_code": load_code, "duration_seconds": load_duration}
    if load_code != 0 or not image_exists(image):
        record["finished_at"] = utc_now()
        record["status"] = "load_failed"
        (case_dir / "run.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return load_code or 1

    inspect = image_inspect(image)
    (case_dir / "image_inspect.json").write_text(
        json.dumps(inspect, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    container_name = f"kt1docs-{package.removeprefix('algo')}-{args.case}".replace("_", "-")
    command = ["docker", "run", "--rm", "--name", container_name]
    if gpu_value is not None:
        command.extend(["--gpus", str(gpu_value)])
    if shm_value is not None:
        command.extend(["--shm-size", str(shm_value)])
    for name, value in runtime_env.items():
        command.extend(["--env", f"{name}={value}"])
    command.extend(
        [
            "--volume",
            f"{input_dir}:/app/data/input:ro",
            "--volume",
            f"{output_dir}:/app/data/output",
            image,
        ]
    )
    command.extend(container_command)
    record["docker_command"] = command
    record["docker_command_shell"] = shlex.join(command)
    record["container_name"] = container_name
    try:
        run_code, run_duration = run_stream(command, case_dir / "docker-run.log")
    except KeyboardInterrupt:
        subprocess.run(
            ["docker", "rm", "--force", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        raise
    output_inventory = inventory(output_dir, hash_files=True)
    (case_dir / "output_inventory.json").write_text(
        json.dumps(output_inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    record["run"] = {"exit_code": run_code, "duration_seconds": run_duration}
    record["output_inventory"] = {
        key: value for key, value in output_inventory.items() if key != "files"
    }
    record["finished_at"] = utc_now()
    if run_code == 0 and output_inventory["file_count"] > 0:
        record["status"] = "completed_with_output"
    elif run_code == 0:
        record["status"] = "completed_without_output"
    else:
        record["status"] = "run_failed"
    (case_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"status={record['status']} exit_code={run_code} output_files={output_inventory['file_count']}")
    return run_code


if __name__ == "__main__":
    raise SystemExit(main())
