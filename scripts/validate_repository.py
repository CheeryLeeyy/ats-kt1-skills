#!/usr/bin/env python3
"""Validate the public ATS topic-one skills repository without external dependencies."""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/ats-kt1-algorithm-docs"
REQUIRED = (
    ROOT / "README.md",
    ROOT / ".gitignore",
    SKILL / "SKILL.md",
    SKILL / "agents/openai.yaml",
    SKILL / "assets/测试说明-示例.docx",
    SKILL / "assets/模型原理说明-示例.docx",
    SKILL / "references/算法提交说明.md",
    SKILL / "references/数据结构规范.md",
    SKILL / "references/模型原理说明模板要求.md",
    SKILL / "scripts/extract_docx_comments.py",
    SKILL / "scripts/extract_existing_diagrams.py",
)
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".txt", ".json", ".gitignore"}
BLOCKED_PATTERNS = {
    "server home path": re.compile(r"/home/ly(?:/|\b)"),
    "server data path": re.compile(r"/mnt/disk2(?:/|\b)"),
    "GitHub classic token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "GitHub fine-grained token": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
}
CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
DC = "{http://purl.org/dc/elements/1.1/}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def text_files() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.name == ".gitignore" or path.suffix.lower() in TEXT_SUFFIXES:
            result.append(path)
    return result


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"required file missing: {path.relative_to(ROOT)}")

    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\nname: ats-kt1-algorithm-docs\ndescription:"):
        errors.append("SKILL.md frontmatter is invalid")
    if skill_text.find("\n---\n", 4) == -1:
        errors.append("SKILL.md frontmatter is not closed")
    if len(skill_text.splitlines()) > 500:
        errors.append("SKILL.md exceeds 500 lines")
    if "TODO" in skill_text:
        errors.append("SKILL.md contains TODO placeholders")
    for required_text in (
        "最新命名 XLSX 是可选输入",
        "从该算法文件夹内已有测试说明或模型原理说明",
        "不使用 `algo1-4-j-N` 文件夹编号冒充模型名称",
        "测试说明参考模板或示例",
        "模型原理说明参考模板或示例",
        "references/模型原理说明模板要求.md",
        "extract_existing_diagrams.py",
        "--missing-only",
        "--preserve-existing-png",
        "中列只写文件级信息",
        "算法根目录中仅用于启动 Docker 的 `params.json`",
        "不罗列文件名、路径、变量名或文件数量",
        "不添加“（节选）”“（结构节选）”等括号补充",
        "支持的协同场景",
        "C、D、E、F 四列",
    ):
        if required_text not in skill_text:
            errors.append(f"SKILL.md is missing required workflow text: {required_text}")
    for required_text in (
        "## 整体运行流程",
        "### 0. 确定算法名称",
        "### 1. 运行 Docker 并同步填写测试说明",
        "### 2. 填写模型原理说明",
        "后续新生成的测试说明和模型原理说明必须全部使用映射表中的最新名称",
        "Docker 实际运行用于核实当前提交包",
        "如果算法文件夹内已有同名模型原理说明",
        "依次使用 `-old-2`、`-old-3`",
        "如果两类旧文档都不存在，继续检查文件夹内的其他 DOCX、PDF、Markdown、TXT 等文档",
        "最新命名 Excel 只能用于确定名称，不能替代算法描述文件",
    ):
        if required_text not in readme_text:
            errors.append(f"README.md is missing required workflow text: {required_text}")

    model_requirement_text = (SKILL / "references/模型原理说明模板要求.md").read_text(
        encoding="utf-8"
    )
    for required_text in (
        "删除“上游接口模型编号”“下游接口模型编号”“交付时间”三行",
        "支持的协同场景",
        "至少写 4 个实质段落",
        "不出现原始论文的英文算法名",
        "每个模块同时给出中文模块名和简短作用说明",
        "按顺序说明数据如何流经各模块",
        "旧图无条件迁移",
        "不得只是框架图的纵向版本",
        "中文文件介绍＋真实文件名",
        "中文介绍＋变量名＋类型＋具体内容",
        "算法根目录中仅用于启动 Docker 的 `params.json`",
    ):
        if required_text not in model_requirement_text:
            errors.append(f"model-principle comment rule is missing: {required_text}")

    agent_text = (SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
    if "$ats-kt1-algorithm-docs" not in agent_text:
        errors.append("agents/openai.yaml default_prompt does not name the skill")

    for generator in (
        SKILL / "scripts/generate_test_doc.py",
        SKILL / "scripts/generate_model_principle_docs.py",
    ):
        generator_text = generator.read_text(encoding="utf-8")
        if "def archive_existing(" not in generator_text or "-old-{index}" not in generator_text:
            errors.append(f"DOCX generator does not archive existing output: {generator.name}")

    for path in text_files():
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"text file is not UTF-8: {path.relative_to(ROOT)}: {exc}")
            continue
        if path.resolve() != Path(__file__).resolve():
            for label, pattern in BLOCKED_PATTERNS.items():
                if pattern.search(value):
                    errors.append(f"{label} found in {path.relative_to(ROOT)}")
        if path.suffix == ".py":
            try:
                compile(value, str(path), "exec")
            except SyntaxError as exc:
                errors.append(f"Python syntax error in {path.relative_to(ROOT)}: {exc}")

    for asset in (SKILL / "assets").glob("*.docx"):
        try:
            with zipfile.ZipFile(asset) as archive:
                corrupt = archive.testzip()
                if corrupt:
                    errors.append(f"corrupt DOCX asset member: {asset.name}: {corrupt}")
                core = ET.fromstring(archive.read("docProps/core.xml"))
                creators = [core.findtext(DC + "creator", ""), core.findtext(CP + "lastModifiedBy", "")]
                if any(value != "ATS课题一" for value in creators):
                    errors.append(f"personal core metadata remains in {asset.name}")
                if "word/comments.xml" in archive.namelist():
                    comments = ET.fromstring(archive.read("word/comments.xml"))
                    comment_nodes = list(comments.iter(W + "comment"))
                    authors = {comment.get(W + "author", "") for comment in comment_nodes}
                    if authors != {"ATS课题一"}:
                        errors.append(f"personal comment author metadata remains in {asset.name}: {sorted(authors)}")
                    if asset.name == "模型原理说明-示例.docx":
                        comment_text = "".join(
                            node.text or "" for comment in comment_nodes for node in comment.iter(W + "t")
                        )
                        if len(comment_nodes) != 3:
                            errors.append(
                                f"model-principle template must retain three comment groups, found {len(comment_nodes)}"
                            )
                        for marker in ("公式和符号", "自己画", "数据流程"):
                            if marker not in comment_text:
                                errors.append(f"model-principle template comment marker missing: {marker}")
        except zipfile.BadZipFile:
            errors.append(f"invalid DOCX asset: {asset.name}")

    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts and path.stat().st_size > 5 * 1024 * 1024:
            errors.append(f"file exceeds 5 MiB public-repository limit: {path.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
