# ATS 课题一 Skills

本仓库包含自主式交通系统（ATS）计算技术课题一算法模型相关的 Skills。仓库结构参考 [jexxl/ats-skills](https://github.com/jexxl/ats-skills)，具体流程、模板和校验规则面向课题一单独维护。

## 包含的 Skill

- `ats-kt1-algorithm-docs`：盘点课题一 Docker 算法包，记录真实输入输出，并按参考模板生成和校验“测试说明”与“模型原理说明” Word 文档；提供最新命名 Excel 时核对“模型名称（现）”，未提供时从算法文件夹内已有文档读取模型名称。

## 使用输入

使用本 Skill 时必须有以下两类参考文档，可以使用项目提供的最新版，也可以使用仓库内置示例：

- 测试说明参考模板或示例：`skills/ats-kt1-algorithm-docs/assets/测试说明-示例.docx`
- 模型原理说明参考模板或示例：`skills/ats-kt1-algorithm-docs/assets/模型原理说明-示例.docx`

最新命名 Excel 是可选项。如果提供，Skill 会检索“模型名称（现）”并按算法编号核对；如果没有，则从每个 `algo1-4-j-N` 算法文件夹内已有的测试说明或模型原理说明读取“模型名称”。项目现场提供的模板优先于仓库内置示例。若 Excel 和内部文档都不能提供模型名称，Skill 会停止并提示补充，不用文件夹编号冒充模型名称。

仓库同时内置 `skills/ats-kt1-algorithm-docs/references/算法提交说明.md`。Docker 运行失败、镜像需要修复或算法提交目录需要整理时，按该规范检查镜像命名、目录布局、输入输出挂载、`params.json` 和 `test_options/`。

## 仓库结构

```text
skills/
└── ats-kt1-algorithm-docs/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── assets/
    ├── references/
    └── scripts/
```

## 安装

推荐使用 `npx skills`：

```bash
npx skills add CheeryLeeyy/ats-kt1-skills --list
npx skills add CheeryLeeyy/ats-kt1-skills --skill ats-kt1-algorithm-docs
```

也可克隆本仓库，将 `skills/ats-kt1-algorithm-docs` 复制或链接到 Agent 的 skills 目录。

## 维护约定

- `main` 只保留通过校验的稳定版本。
- 模板、结构化数据规范或生成器变更使用独立分支和 Pull Request。
- 提交前运行 `python scripts/validate_repository.py`。
- 不提交算法镜像、业务数据、实测输出、已生成文档或服务器绝对路径。

## 运行环境

Word 生成和大部分校验脚本仅使用 Python 标准库。Docker 实测需要 Docker CLI，SVG 转 PNG 和 DOCX 视觉检查需要 LibreOffice。

## 许可

本仓库采用 [MIT License](LICENSE) 开源许可。

## 致谢

感谢 [jexxl/ats-skills](https://github.com/jexxl/ats-skills) 提供的仓库结构和 Skills 组织思路，本项目在此基础上结合自主式交通系统（ATS）计算技术课题一的算法模型文档要求进行了定制。
