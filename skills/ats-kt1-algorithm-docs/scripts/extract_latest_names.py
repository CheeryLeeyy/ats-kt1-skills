#!/usr/bin/env python3
"""Extract algorithm identifiers and current model names from the naming XLSX."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--first", type=int)
    parser.add_argument("--last", type=int)
    args = parser.parse_args()
    if (args.first is None) != (args.last is None):
        parser.error("--first and --last must be supplied together")
    if args.first is not None and args.first > args.last:
        parser.error("--first must not be greater than --last")

    rows = load_rows(args.xlsx)
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
        if args.first is not None and not args.first <= number <= args.last:
            continue
        current_name = row.get(name_column, "").strip()
        if not current_name:
            raise ValueError(f"missing 模型名称（现） for {algorithm_id}")
        result[f"1-4-J-{number}"] = {
            "number": number,
            "package": f"algo1-4-j-{number}",
            "original_name": row.get(original_name_column, "").strip() if original_name_column else "",
            "current_name": current_name,
        }

    if args.first is not None:
        expected = {f"1-4-J-{number}" for number in range(args.first, args.last + 1)}
        missing = sorted(expected - result.keys(), key=lambda item: int(item.rsplit("-", 1)[1]))
        if missing:
            raise ValueError(f"missing identifiers in workbook: {missing}")
    if not result:
        raise ValueError("no topic-one algorithm identifiers were found")

    payload = {
        "source": str(args.xlsx),
        "sheet": "工作表1",
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
