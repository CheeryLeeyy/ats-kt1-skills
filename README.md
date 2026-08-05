# ATS 课题一 Skills

本仓库包含自主式交通系统（ATS）计算技术课题一算法模型相关的 Skills。仓库结构参考 [jexxl/ats-skills](https://github.com/jexxl/ats-skills)，具体流程、模板和校验规则面向课题一单独维护。

## 包含的 Skill

- `ats-kt1-algorithm-docs`：盘点课题一 Docker 算法包，核对最新模型命名，记录真实输入输出，生成并校验“测试说明”和“模型原理说明” Word 文档。

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

本仓库尚未声明开源许可证。在添加许可证前，默认保留所有权利。
