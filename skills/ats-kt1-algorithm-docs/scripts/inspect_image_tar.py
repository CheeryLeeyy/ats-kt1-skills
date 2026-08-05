#!/usr/bin/env python3
"""Read Docker/OCI save metadata without loading the image."""

from __future__ import annotations

import argparse
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json_member(archive: tarfile.TarFile, name: str) -> Any:
    member = archive.getmember(name)
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError(f"cannot read archive member: {name}")
    return json.load(stream)


def selected_config(config: dict[str, Any]) -> dict[str, Any]:
    runtime = config.get("config") or {}
    container = config.get("container_config") or {}
    return {
        "id": config.get("id"),
        "created": config.get("created"),
        "architecture": config.get("architecture"),
        "os": config.get("os"),
        "author": config.get("author"),
        "working_dir": runtime.get("WorkingDir") or container.get("WorkingDir"),
        "entrypoint": runtime.get("Entrypoint") or container.get("Entrypoint"),
        "cmd": runtime.get("Cmd") or container.get("Cmd"),
        "env": runtime.get("Env") or container.get("Env") or [],
        "labels": runtime.get("Labels") or container.get("Labels") or {},
        "history": [
            {
                "created": item.get("created"),
                "created_by": item.get("created_by"),
                "comment": item.get("comment"),
                "empty_layer": item.get("empty_layer", False),
            }
            for item in config.get("history", [])
        ],
    }


def inspect(path: Path) -> dict[str, Any]:
    stat = path.stat()
    result: dict[str, Any] = {
        "archive": str(path.resolve()),
        "archive_size_bytes": stat.st_size,
        "archive_mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }
    with tarfile.open(path, "r:*") as archive:
        names = {member.name for member in archive.getmembers()}
        if "manifest.json" not in names:
            raise ValueError("archive does not contain manifest.json")
        manifest = read_json_member(archive, "manifest.json")
        if not isinstance(manifest, list) or not manifest:
            raise ValueError("manifest.json contains no images")
        images = []
        for item in manifest:
            config_name = item.get("Config")
            if not config_name or config_name not in names:
                raise ValueError(f"missing image config: {config_name}")
            config = read_json_member(archive, config_name)
            layer_names = item.get("Layers") or []
            layer_sizes = []
            for layer in layer_names:
                try:
                    layer_sizes.append(archive.getmember(layer).size)
                except KeyError:
                    layer_sizes.append(None)
            images.append(
                {
                    "repo_tags": item.get("RepoTags") or [],
                    "config_member": config_name,
                    "config": selected_config(config),
                    "layers": layer_names,
                    "layer_sizes_bytes": layer_sizes,
                    "layer_count": len(layer_names),
                    "declared_layer_bytes": sum(size or 0 for size in layer_sizes),
                }
            )
        result["images"] = images
        result["archive_format"] = "oci-layout" if "oci-layout" in names else "docker-save"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Docker/OCI image tar")
    parser.add_argument("--output", type=Path, help="write UTF-8 JSON here")
    args = parser.parse_args()
    data = inspect(args.archive)
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
