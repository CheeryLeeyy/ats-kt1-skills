#!/usr/bin/env python3
"""Replace personal DOCX metadata while preserving template comments and formatting."""

from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
DC = "{http://purl.org/dc/elements/1.1/}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def sanitize(path: Path, author: str, initials: str) -> None:
    with zipfile.ZipFile(path) as source:
        members = [(info, source.read(info.filename)) for info in source.infolist()]
    updated: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info, payload in members:
        if info.filename == "docProps/core.xml":
            root = ET.fromstring(payload)
            creator = root.find(DC + "creator")
            modifier = root.find(CP + "lastModifiedBy")
            if creator is not None:
                creator.text = author
            if modifier is not None:
                modifier.text = author
            payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        elif info.filename == "word/comments.xml":
            root = ET.fromstring(payload)
            for comment in root.iter(W + "comment"):
                comment.set(W + "author", author)
                comment.set(W + "initials", initials)
            payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        updated.append((info, payload))

    fd, temp_name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".docx", dir=path.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for info, payload in updated:
                target.writestr(info, payload)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", nargs="+", type=Path)
    parser.add_argument("--author", default="ATS课题一")
    parser.add_argument("--initials", default="ATS")
    args = parser.parse_args()
    for path in args.docx:
        sanitize(path, args.author, args.initials)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
