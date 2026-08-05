#!/usr/bin/env python3
"""Capture Docker/GPU/disk state for a before/after cleanup comparison."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def command(argv: list[str], check: bool = True) -> str:
    result = subprocess.run(
        argv,
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return result.stdout.strip()


def json_lines(text: str) -> list[Any]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work-path", required=True, type=Path)
    args = parser.parse_args()
    docker_root = command(["docker", "info", "--format", "{{.DockerRootDir}}"])
    data = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "docker_root": docker_root,
        "images": json_lines(
            command(
                [
                    "docker",
                    "image",
                    "ls",
                    "--all",
                    "--digests",
                    "--no-trunc",
                    "--format",
                    "{{json .}}",
                ]
            )
        ),
        "containers": json_lines(
            command(["docker", "container", "ls", "--all", "--no-trunc", "--format", "{{json .}}"])
        ),
        "docker_system_df": command(["docker", "system", "df"]),
        "filesystems": {
            "work": shutil.disk_usage(args.work_path.resolve())._asdict(),
            "docker_root": shutil.disk_usage(Path(docker_root).resolve())._asdict(),
        },
    }
    nvidia = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    data["nvidia_smi"] = nvidia.stdout.strip() if nvidia.returncode == 0 else nvidia.stderr.strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
