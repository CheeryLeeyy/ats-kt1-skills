#!/usr/bin/env python3
"""Resolve model names from an optional naming XLSX or existing DOCX files."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PACKAGE_PATTERN = re.compile(r"algo1-4-j-(\d+)", re.IGNORECASE)
DOCUMENT_SUFFIXES = {".docx", ".doc", ".pdf", ".md", ".txt"}
MODEL_NAME_PATTERN = re.compile(
    r"^\s*模型名称(?:（现）)?(?:\d+)?\s*(?:[:：]\s*)?(.*?)\s*$"
)
MARKDOWN_MODEL_NAME_PATTERN = re.compile(r"^\s*\|\s*模型名称\s*\|\s*([^|]+?)\s*\|?\s*$")


def cell_column(reference: str) -> str:
    match = re.match(r"([A-Z]+)", reference)
    if not match:
        raise ValueError(f"invalid cell reference: {reference}")
    return match.group(1)


def rich_text(node: ET.Element) -> str:
    return "".join(item.text or "" for item in node.findall(".//x:t", NS))


def load_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        shared = [rich_text(item) for item in shared_root.findall("x:si", NS)]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows: list[dict[str, str]] = []
    for row in sheet.findall(".//x:sheetData/x:row", NS):
        values: dict[str, str] = {}
        for cell in row.findall("x:c", NS):
            reference = cell.attrib["r"]
            column = cell_column(reference)
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                inline = cell.find("x:is", NS)
                value = rich_text(inline) if inline is not None else ""
            else:
                raw = cell.findtext("x:v", default="", namespaces=NS)
                value = shared[int(raw)] if cell_type == "s" and raw else raw
            values[column] = value.strip()
        rows.append(values)
    return rows


def discover_packages(root: Path, first: int | None, last: int | None) -> list[tuple[int, str]]:
    if not root.is_dir():
        raise ValueError(f"algorithm root is not a directory: {root}")
    packages: list[tuple[int, str]] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        match = PACKAGE_PATTERN.fullmatch(path.name)
        if not match:
            continue
        number = int(match.group(1))
        if first is not None and not first <= number <= last:
            continue
        packages.append((number, path.name))
    packages.sort()
    if not packages:
        raise ValueError("no topic-one algorithm folders were found")
    return packages


def docx_paragraphs(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise ValueError(f"cannot read DOCX {path}: {exc}") from exc
    paragraphs: list[str] = []
    for paragraph in document.iter(W + "p"):
        value = "".join(node.text or "" for node in paragraph.iter(W + "t")).strip()
        if value:
            paragraphs.append(value)
    return paragraphs


def extract_model_name(path: Path) -> str | None:
    if path.suffix.lower() == ".docx":
        paragraphs = docx_paragraphs(path)
    elif path.suffix.lower() in {".md", ".txt"}:
        paragraphs = path.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        return None
    for index, paragraph in enumerate(paragraphs):
        markdown_match = MARKDOWN_MODEL_NAME_PATTERN.fullmatch(paragraph)
        if markdown_match:
            return markdown_match.group(1).strip()
        match = MODEL_NAME_PATTERN.fullmatch(paragraph)
        if not match:
            continue
        inline_value = match.group(1).strip()
        if inline_value:
            return inline_value
        if index + 1 < len(paragraphs):
            next_value = paragraphs[index + 1].strip()
            if next_value and not MODEL_NAME_PATTERN.fullmatch(next_value):
                return next_value
    return None


def document_priority(path: Path) -> tuple[int, int, str]:
    name = path.name.lower()
    if "模型原理说明" in name:
        document_type = 0
    elif "测试说明" in name:
        document_type = 1
    else:
        document_type = 2
    old_marker = 1 if "old" in name else 0
    return document_type, old_marker, name


def reference_documents(package_dir: Path) -> list[Path]:
    documents = [
        path
        for path in package_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in DOCUMENT_SUFFIXES
    ]
    preferred = [
        path
        for path in documents
        if "测试说明" in path.name or "模型原理说明" in path.name
    ]
    return sorted(preferred or documents, key=document_priority)


def require_reference_documents(package_dir: Path) -> list[Path]:
    candidates = reference_documents(package_dir)
    if not candidates:
        raise ValueError(
            "no existing test-description, model-principle, or other supporting document under "
            f"{package_dir}; stop and request a detailed model-algorithm description file"
        )
    return candidates


def name_from_existing_documents(package_dir: Path) -> tuple[str, Path]:
    candidates = require_reference_documents(package_dir)
    unreadable: list[str] = []
    for path in candidates:
        try:
            model_name = extract_model_name(path)
        except ValueError as exc:
            unreadable.append(str(exc))
            continue
        if model_name:
            return model_name, path
    detail = f"; unreadable documents: {unreadable}" if unreadable else ""
    raise ValueError(
        f"could not find a 模型名称 field in existing supporting documents under {package_dir}{detail}"
    )


def load_workbook_names(path: Path) -> tuple[dict[str, dict[str, str]], str, str]:
    rows = load_rows(path)
    header_index = next(
        index
        for index, row in enumerate(rows)
        if "模型名称（现）" in row.values()
    )
    header = rows[header_index]
    columns = {value: column for column, value in header.items()}
    name_column = columns["模型名称（现）"]

    id_column = None
    for candidate in ("算法编号", "模型编号", "编号"):
        if candidate in columns:
            id_column = columns[candidate]
            break
    if id_column is None:
        for column in header:
            if any(re.fullmatch(r"1-4-J-\d+", row.get(column, "")) for row in rows[header_index + 1 :]):
                id_column = column
                break
    if id_column is None:
        raise ValueError("could not identify the algorithm-id column")

    original_name_column = columns.get("模型名称（原）")
    result: dict[str, dict[str, str]] = {}
    for row in rows[header_index + 1 :]:
        algorithm_id = row.get(id_column, "").strip()
        match = re.fullmatch(r"1-4-J-(\d+)", algorithm_id, re.IGNORECASE)
        if not match:
            continue
        number = int(match.group(1))
        current_name = row.get(name_column, "").strip()
        if not current_name:
            continue
        result[f"1-4-J-{number}"] = {
            "number": number,
            "package": f"algo1-4-j-{number}",
            "original_name": row.get(original_name_column, "").strip() if original_name_column else "",
            "current_name": current_name,
            "name_source": str(path),
        }
    return result, id_column, name_column


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--algorithms-root", required=True, type=Path)
    parser.add_argument("--xlsx", type=Path, help="optional workbook containing 模型名称（现）")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--first", type=int)
    parser.add_argument("--last", type=int)
    args = parser.parse_args()
    if (args.first is None) != (args.last is None):
        parser.error("--first and --last must be supplied together")
    if args.first is not None and args.first > args.last:
        parser.error("--first must not be greater than --last")

    try:
        packages = discover_packages(args.algorithms_root, args.first, args.last)
    except ValueError as exc:
        parser.error(str(exc))
    workbook_available = args.xlsx is not None and args.xlsx.is_file()
    if args.xlsx is not None and not workbook_available:
        print(f"WARNING: naming workbook not found: {args.xlsx}", file=sys.stderr)
        print("WARNING: resolving names from existing DOCX files", file=sys.stderr)

    if workbook_available:
        try:
            workbook_names, id_column, name_column = load_workbook_names(args.xlsx)
        except (KeyError, StopIteration, ValueError, zipfile.BadZipFile) as exc:
            parser.error(f"cannot read naming workbook {args.xlsx}: {exc}")
        result: dict[str, dict[str, str]] = {}
        missing: list[str] = []
        for number, package in packages:
            algorithm_id = f"1-4-J-{number}"
            package_dir = args.algorithms_root / package
            try:
                require_reference_documents(package_dir)
            except ValueError as exc:
                parser.error(str(exc))
            item = workbook_names.get(algorithm_id)
            if item is None:
                missing.append(algorithm_id)
                continue
            try:
                existing_name, existing_source = name_from_existing_documents(
                    package_dir
                )
            except ValueError:
                existing_name = ""
                existing_source = None
            result[algorithm_id] = {
                **item,
                "package": package,
                "existing_document_name": existing_name,
                "existing_document_source": str(existing_source) if existing_source else "",
                "name_matches_existing_document": (
                    item["current_name"] == existing_name if existing_name else None
                ),
            }
        if missing:
            parser.error(f"algorithm folders missing from naming workbook: {missing}")
        source = str(args.xlsx)
        naming_mode = "workbook"
    else:
        id_column = None
        name_column = None
        result = {}
        for number, package in packages:
            package_dir = args.algorithms_root / package
            try:
                current_name, name_source = name_from_existing_documents(package_dir)
            except ValueError as exc:
                parser.error(str(exc))
            result[f"1-4-J-{number}"] = {
                "number": number,
                "package": package,
                "original_name": "",
                "current_name": current_name,
                "name_source": str(name_source),
            }
        source = None
        naming_mode = "existing-document"

    payload = {
        "naming_mode": naming_mode,
        "source": source,
        "sheet": "工作表1" if workbook_available else None,
        "id_column": id_column,
        "current_name_column": name_column,
        "algorithms": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    for algorithm_id, item in result.items():
        print(f"{algorithm_id}\t{item['current_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
