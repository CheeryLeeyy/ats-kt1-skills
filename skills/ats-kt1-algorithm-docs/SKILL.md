---
name: ats-kt1-algorithm-docs
description: 为自主式交通系统（ATS）计算技术课题一 Docker 算法检查提交包、实测输入输出，并按参考 Word 模板或示例生成和更新测试说明与模型原理说明；可选使用最新命名 Excel 核对模型名称，没有命名表时从算法文件夹内已有文档读取名称。当需要整理 algo1-4-j-N 算法、input/output/test_options/params.json、Docker 运行证据、旧说明文档、模型输入输出或批量校验 DOCX 时使用。
---

# ATS 课题一算法文档

## 原则

以当前算法包、可选最新命名表、真实 Docker 入口和可解析输出为主要事实来源。仅从同一算法目录的旧测试说明或模型原理说明补充本次输出缺少的同名指标；不跨算法借值，不虚构未运行的数据。文档直接使用既有指标名称和补充值，不记录指标数据来源。

不在 Word 中记录 tar 索引、镜像标签修复、代码修复、容器告警或 `smoke` 运行模式。将这些信息仅保存在内部 evidence 中。

## 输入与必须读取

- 开始前完整读取 `references/算法提交说明.md`；Docker 运行失败、修复镜像、整理提交目录或调整 `params.json` 时重新对照该文件逐项检查。
- 准备结构化数据时读取 `references/数据结构规范.md`。
- 填写模型原理说明前完整读取 `references/模型原理说明模板要求.md`，逐条落实从模板批注整理出的规则。
- 生成测试说明前必须取得一份测试说明参考模板或示例；默认使用 `assets/测试说明-示例.docx`。
- 生成模型原理说明前必须取得一份模型原理说明参考模板或示例；默认使用 `assets/模型原理说明-示例.docx`。
- 将模板批注作为编写要求，最终 Word 不保留批注、批注锚点或兼容性残留。

用户提供的现场模板或示例优先于 skill 内置资产。两类文档的参考模板或示例均不可用时，停止生成并请求提供，不自行猜测版式。现场文件与 skill 资产不同时，记录实际使用文件的 SHA-256。

最新命名 XLSX 是可选输入。有可用文件时，读取“模型名称（现）”并按算法编号核对；没有时，优先从该算法文件夹内已有测试说明或模型原理说明的“模型名称”字段读取，两类旧文档缺失时再从其他相关文档读取。没有 Excel 且内部文档也没有可识别名称时，停止并请求补充名称，不使用 `algo1-4-j-N` 文件夹编号冒充模型名称。内部文档仅作为无命名表时的回退来源，不能替代已经提供的最新命名表。

优先将算法文件夹内的旧测试说明和旧模型原理说明作为算法事实来源。两类旧文档都不存在时，继续检查同目录及其子目录中的其他 DOCX、PDF、Markdown、TXT 等文档；只有文档确实包含算法原理、模块组成、处理流程、输入输出、指标或性能说明时才作为替代事实来源。若没有任何相关内容，无论是否有最新命名 Excel，都立即停止，不运行 Docker、不生成新文档，并请求用户提供详细的模型算法描述文件。命名表不能替代算法描述文件。

## 目录与命名

从目录名解析编号，不从文档正文猜测：

```text
算法目录：algo1-4-j-N
业务编号：1-4-J-N
镜像标签：algo1-4-j-N:v1
测试说明：algo1-4-j-N测试说明.docx
模型原理说明：algo1-4-j-N模型原理说明.docx
```

始终从实际算法根目录发现待处理文件夹。`--xlsx` 可省略；提供且文件存在时，从“模型名称（现）”列获取名称并与目录编号核对，不用旧 Word 的名称代替：

```bash
python scripts/extract_latest_names.py \
  --algorithms-root /path/to/unzips \
  --xlsx /path/to/课题一最新命名.xlsx \
  --output /work/latest_names.json \
  --first 1 --last 10
```

没有最新命名 Excel 时省略 `--xlsx`，脚本会从各算法文件夹内已有 DOCX 的“模型名称”字段写入 `current_name`：

```bash
python scripts/extract_latest_names.py \
  --algorithms-root /path/to/unzips \
  --output /work/latest_names.json \
  --first 1 --last 10
```

生成新文档前先完成对旧文档的名称和内容提取。算法目录中已有同名测试说明或模型原理说明时，在扩展名前加 `-old` 归档旧文件；若归档目标已存在，依次使用 `-old-2`、`-old-3`。不得直接覆盖旧文档。

## 执行顺序

同时更新两类文档时，严格按 0→1→2 执行：

### 0. 确定名称

盘点参考模板和算法文件夹内已有 Word。既没有旧测试说明也没有旧模型原理说明时，检查其他文档是否包含相关算法内容；存在相关内容则作为替代依据，完全没有时请求详细模型算法描述文件并停止后续工作。有最新命名 Excel 时，按算法编号比较“模型名称（现）”与内部文档名称；不同时将最新名称用于后续所有新文档的基本信息、正文和图表，相同时沿用内部文档名称。没有 Excel 时读取内部文档的“模型名称”。两种来源都无法提供名称时停止并请求补充。

### 1. 运行 Docker 并同步填写测试说明

先从同一算法的旧测试说明和模型原理说明提取算法功能、输入输出语义、文件与字段名称、指标名称、单位、已有数值和性能结论，作为内容基线。再实际运行 Docker，边检查输入输出边填写测试说明，用实测过程核实具体目录、格式、字段、运行配置、输出产物和命令行结果。保持旧文档中的输入输出与指标表述，不随意删改；本次输出缺少既有指标时从同一算法旧文档补充。

Docker 失败时，按照 `references/算法提交说明.md` 检查并最小修正镜像、目录结构、入口、挂载、`params.json` 和运行资源。必须从算法目录内最终镜像重新加载并成功复测后，才能完成测试说明。保存命令、时长、退出码、日志和可解析输出作为内部证据，不把修复过程写进最终 Word。

### 2. 填写模型原理说明

先生成并校验测试说明，再填写模型原理说明。以同一算法的旧模型原理说明保持算法设计与模块细节一致，从已校验测试 JSON 直接复用输入、输出、格式、字段和指标说明，并使用步骤 0 确定的统一名称。生成器写入新模型原理说明前必须将已有同名文档归档为 `-old`、`-old-2`、`-old-3`。最后使用 LibreOffice 打开或转换两类 Word，逐页检查版式并清理临时件和本次加载的 Docker 对象。

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
- 基本信息表中仅将最左侧“输入数据要求”标题单元格向下合并到最后一条输入明细；“输出数据要求”从自己的标题行重新开始，并仅向下合并到最后一条输出明细。两个合并区互不越界，右侧摘要和“文件名／字段说明”列不做纵向合并。
- 将 `2 算法模型简介` 写成至少 4 个有实质内容且合计不少于 350 个中文字符的段落，说明问题、组成模块、处理链路和关键配置/输出；适合时使用公式和符号并解释含义。
- 不写与自主式交通系统或当前算法无关的文字和图片；正文不出现原始论文的英文算法名、英文模型名、英文模块名或英文全称，改写为准确的中文功能名称。
- 先从旧模型原理说明直接提取内嵌的框架图和流程图。旧图与最新名称、当前输入输出和模块设计一致时复制复用，不对旧 Word 截图；缺少或过时的图才根据当前算法自行绘制，不使用论文、网页或运行界面截图。旧图含少量只用于辅助标注的英文名称时，若正文未使用、也不代表整个算法或关键模块，可以保留。
- 明确区分两图：框架图介绍子模块、模块职责和模块间关系，每个模块写明中文名称和作用；流程图从真实输入到真实输出说明先后步骤以及数据的读取、处理、传递、融合和写出方式。不得将同一组模块简单换序或换版式充当两幅图；两图输入输出必须与测试说明一致。
- 按模板要求将上游接口模型编号、下游接口模型编号和交付时间留空。

使用下列命令检查当前模型原理说明模板批注；现场模板不同时也运行一次并逐条核对：

```bash
python scripts/extract_docx_comments.py \
  --docx assets/模型原理说明-示例.docx
```

先为每个算法编写简介与六节点框架 spec。随后从旧模型原理说明提取可复用图片，再以 `--missing-only` 只生成缺少的图：

```bash
python scripts/prepare_model_principle_data.py \
  --names /work/latest_names.json \
  --test-data-dir /work/test-data \
  --spec-dir /work/model-specs \
  --output-dir /work/model-data
python scripts/extract_existing_diagrams.py \
  --docx /path/to/algo1-4-j-N模型原理说明-old.docx \
  --package algo1-4-j-N \
  --output-dir /work/diagrams \
  --manifest /work/diagrams/algo1-4-j-N-existing.json
python scripts/generate_diagrams.py \
  --data-dir /work/model-data --output-dir /work/diagrams --missing-only
python scripts/render_svg_diagrams.py \
  --svg-dir /work/diagrams --output-dir /work/diagrams \
  --preserve-existing-png
python scripts/generate_model_principle_docs.py \
  --template assets/模型原理说明-示例.docx \
  --data-dir /work/model-data --diagrams /work/diagrams \
  --output-dir /work/docs
python scripts/validate_model_principle_docs.py \
  --docx /work/docs/algo1-4-j-N模型原理说明.docx \
  --data /work/model-data/algo1-4-j-N.json
```

旧模型原理说明不存在或没有可识别图片时，跳过提取命令，`--missing-only` 会生成两幅图。提取后必须人工查看复用图；含错误输入输出、以旧英文名称代表整个算法或关键模块、论文截图、无关内容或不可读文字时删除对应提取结果，让生成器补画；只有少量非关键英文辅助标注时可以保留。

## 校验与清理

用 LibreOffice 使用独立临时用户配置打开或转换每份 DOCX，逐页检查标题、分页、表格跨页、代码换行、中文字体、框架图和流程图。当 Word 提示不可读内容时，先检查 DOCX ZIP 完整性、关系目标、`mc:Ignorable`、`w14` 属性和批注元数据。

完成后只删除本次创建的临时解包目录、渲染 PDF/PNG、LibreOffice 配置、Python 缓存、可重建运行输出副本、容器和镜像标签。不使用无范围的 Docker prune，不删除任务前已存在的 Docker 资产。保留最终 Word、结构化数据、生成/校验脚本和支撑文档事实的精简证据。
