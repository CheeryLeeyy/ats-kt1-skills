#!/usr/bin/env python3
"""Render generated SVG diagrams to PNG with an isolated LibreOffice profile."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--libreoffice", default="libreoffice")
    args = parser.parse_args()
    svg_files = sorted(args.svg_dir.glob("algo1-4-j-*.svg"))
    if not svg_files:
        raise ValueError("no generated SVG diagrams found")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ats-kt1-svg-") as profile:
        environment = dict(os.environ)
        environment.setdefault("SAL_USE_VCLPLUGIN", "svp")
        for path in svg_files:
            command = [
                args.libreoffice,
                f"-env:UserInstallation=file://{profile}",
                "--headless",
                "--convert-to",
                "png",
                "--outdir",
                str(args.output_dir),
                str(path),
            ]
            completed = subprocess.run(command, text=True, capture_output=True, env=environment)
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(f"failed to render {path.name}: {detail}")
            output = args.output_dir / f"{path.stem}.png"
            if not output.is_file():
                detail = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
                raise RuntimeError(f"LibreOffice did not render {path.name}: {detail}")

    for path in svg_files:
        print(args.output_dir / f"{path.stem}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
