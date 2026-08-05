---
name: ats-kt1-algorithm-docs
description: 为自主式交通系统（ATS）计算技术课题一 Docker 算法检查提交包、实测输入输出、核对最新模型命名，并按指定 Word 模板生成或更新测试说明与模型原理说明。当需要整理 algo1-4-j-N 算法、input/output/test_options/params.json、Docker 运行证据、旧说明文档、最新命名表、模型输入输出或批量校验 DOCX 时使用。
---

# ATS 课题一算法文档

## 原则

以当前算法包、最新命名表、真实 Docker 入口和可解析输出为主要事实来源。仅从同一算法目录的旧测试说明或模型原理说明补充本次输出缺少的同名指标；不跨算法借值，不虚构未运行的数据。文档直接使用既有指标名称和补充值，不记录指标数据来源。

不在 Word 中记录 tar 索引、镜像标签修复、代码修复、容器告警或 `smoke` 运行模式。将这些信息仅保存在内部 evidence 中。

## 必须读取

- 开始前完整读取 `references/算法提交说明.md`。
- 准备结构化数据时读取 `references/数据结构规范.md`。
- 生成测试说明时使用 `assets/测试说明-示例.docx`。
- 生成模型原理说明时使用 `assets/模型原理说明-示例.docx`。
- 将模板批注作为编写要求，最终 Word 不保留批注、批注锚点或兼容性残留。

现场文件与 skill 资产不同时，优先使用用户明确指定的现场模板和提交说明，并记录 SHA-256。

## 目录与命名

从目录名解析编号，不从文档正文猜测：

```text
算法目录：algo1-4-j-N
业务编号：1-4-J-N
镜像标签：algo1-4-j-N:v1
测试说明：algo1-4-j-N测试说明.docx
模型原理说明：algo1-4-j-N模型原理说明.docx
```

当任务要求最新名称时，从命名 XLSX 的“模型名称（现）”列获取，不用旧 Word 的名称代替。运行：

```bash
python scripts/extract_latest_names.py \
  --xlsx /path/to/课题一最新命名.xlsx \
  --output /work/latest_names.json \
  --first 1 --last 10
```

算法目录中已有测试说明时，生成新文档前将旧文件在扩展名前加 `-old`；若目标已存在，使用 `-old-2`、`-old-3`。模型原理说明只读参考，除非用户明确要求，不改名或覆盖。

## 执行顺序

同时更新两类文档时，严格按以下顺序：

1. 从命名表确定当前名称。
2. 盘点算法包、输入、可替换样例、运行配置、旧 Word 和镜像入口。
3. 实际运行 Docker，保存命令、时长、退出码、日志和可解析输出。
4. 编写、生成并校验测试说明。
5. 从已校验测试 JSON 直接复用输入、输出、格式和字段解释，再生成模型原理说明。
6. 使用 LibreOffice 打开或转换所有 Word，完成逐页排版检查后清理临时件和本次加载的 Docker 对象。

## 并行策略

并行执行只读盘点、旧 Word 文字提取、镜像 tar 元数据分析和不同算法的文档校验。默认按用户指定顺序串行加载和运行 Docker。只在确认磁盘、GPU、内存、端口和输出目录相互独立时做有界并行。不允许多个任务同时写同一目录、改名同一文档或删除同一镜像标签。

## Docker 检查与实验

使用以下脚本生成可复核证据：

```bash
python scripts/inspect_image_tar.py /path/to/algo1-4-j-N.tar \
  --output /work/evidence/algo1-4-j-N/image.json
python scripts/capture_docker_state.py --output /work/evidence/docker-before.json
python scripts/run_docker_experiment.py --help
python scripts/summarize_run_output.py --help
```

每次运行前检查 Docker Root Dir 和数据盘空间，校验 `params.json` 是合法 JSON。将输入只读挂载到 `/app/data/input`，将独立输出目录挂载到 `/app/data/output`：

```bash
docker run --rm \
  --volume /absolute/input:/app/data/input:ro \
  --volume /absolute/output:/app/data/output \
  [params.json 中的额外参数] \
  algo1-4-j-N:v1
```

注意 `:ro` 只出现在输入挂载末尾，表示容器对输入只读；输出挂载不加 `:ro`。`params.json`、GPU、共享内存和模型入口是每次运行配置，不是可泛化输入样例。

默认入口失败时，先排查输入布局、挂载、标签、工作目录、入口命令和运行资源。只在用户授权时按提交规范做最小原地修复。修复镜像后，从算法目录的最终 tar 重新加载并复测；不只验证内存中的中间镜像。

## 测试说明

为每个算法准备一份测试 JSON，严格区分真实输入样例、Docker 运行配置和预期输出。使用当前名称独立编写模型介绍、字段解释和通过条件，不机械复制模板文字。

保留以下章节顺序：

1. `1 测试数据与配置`
2. `1.1 测试输入文件清单`
3. `1.2 实际输入数据`
4. `1.3 可泛化样例`：只写 `test_options/` 中真实存在、可完整替换 `input/` 的样例
5. `2 测试过程`
6. `2.1 Docker运行配置`：写 params.json、GPU、共享内存和默认入口
7. `2.2 Docker运行命令`：写镜像加载和 Linux/macOS、Windows PowerShell 命令
8. `3 预期测试结果`：逐一说明 output 预期文件、格式、结构、字段和命令行预期结果
9. `4 测试通过条件`：说明预期产物、内容和可满足的业务需求

第 2 章不保留“输出文件清单”标题或表格。输出清单与字段解释只放在第 3 章。生成与校验：

```bash
python scripts/generate_test_doc.py \
  --template assets/测试说明-示例.docx \
  --data /work/test-data/algo1-4-j-N.json \
  --output /work/docs/algo1-4-j-N测试说明.docx
python scripts/validate_test_doc.py \
  --docx /work/docs/algo1-4-j-N测试说明.docx \
  --data /work/test-data/algo1-4-j-N.json
```

## 模型原理说明

以同一算法的旧模型原理说明作为设计与模块细节依据，使用当前名称按最新模板重建。不复制过时名称、错误图示或其他算法内容。

- 从已校验的测试 JSON 直接复用输入/输出文件名、格式、字段和中文解释。
- 将 `2 算法模型简介` 写成至少 4 个有实质内容的段落，说明问题、组成模块、处理链路和关键配置/输出。
- 根据当前算法自行绘制框架图和流程图，不使用论文、旧 Word 或运行界面截图。
- 按模板要求将上游接口模型编号、下游接口模型编号和交付时间留空。

先为每个算法编写简介与六节点框架 spec，再运行：

```bash
python scripts/prepare_model_principle_data.py \
  --names /work/latest_names.json \
  --test-data-dir /work/test-data \
  --spec-dir /work/model-specs \
  --output-dir /work/model-data
python scripts/generate_diagrams.py \
  --data-dir /work/model-data --output-dir /work/diagrams
python scripts/render_svg_diagrams.py \
  --svg-dir /work/diagrams --output-dir /work/diagrams
python scripts/generate_model_principle_docs.py \
  --template assets/模型原理说明-示例.docx \
  --data-dir /work/model-data --diagrams /work/diagrams \
  --output-dir /work/docs
python scripts/validate_model_principle_docs.py \
  --docx /work/docs/algo1-4-j-N模型原理说明.docx \
  --data /work/model-data/algo1-4-j-N.json
```

## 校验与清理

用 LibreOffice 使用独立临时用户配置打开或转换每份 DOCX，逐页检查标题、分页、表格跨页、代码换行、中文字体、框架图和流程图。当 Word 提示不可读内容时，先检查 DOCX ZIP 完整性、关系目标、`mc:Ignorable`、`w14` 属性和批注元数据。

完成后只删除本次创建的临时解包目录、渲染 PDF/PNG、LibreOffice 配置、Python 缓存、可重建运行输出副本、容器和镜像标签。不使用无范围的 Docker prune，不删除任务前已存在的 Docker 资产。保留最终 Word、结构化数据、生成/校验脚本和支撑文档事实的精简证据。
