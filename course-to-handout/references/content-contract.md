# v2 内容、证据与核验协议

程序入口：`lecture.py contract` 给最小单元；`scaffold JOB` 创建文档。`unit-put JOB FILE.json|FILE.yaml` 校验局部单元并写规范 JSON，保留已有单元顺序；全局用 `check JOB`。所有时间为视频起点起的秒，原素材不因教学切分而改时刻。

## 文档和单元

handout.json 的 schema_version=2，包含 title、level、prerequisites[]、learning_goal、coverage、sections[]、units[]、figures[]。section 包含 id、title、start、end；区间合法且可重叠。coverage 记录 included、omitted 及其原因、素材/修订依据。工作目录 source.json 确定 video_id、part、duration、url。

unit 字段：

| 字段 | 语义 |
|---|---|
| id / section_id | 稳定 ASCII 单元标识 / 已存在章节 |
| type | definition、theorem、example、note、exercise |
| title | 学生可读语义名称 |
| origin | course、ai_supplement、generated、comment、external，表示题干或内容来源 |
| answer_origin | course、ai_supplement、generated、external，单独表示答案来源 |
| conditions[] | 必要假设；正文题干/定理也须让学生读到 |
| body[] | 定义正文或完整题干 |
| motivation | 方法为什么适合本题 |
| steps[] | heading、content[]；可有 basis、show_reason，默认不逐步打印依据 |
| conclusion[] / pitfalls[] | 结果 / 有教学价值的提醒 |
| sources[] / evidence[] | 语义时间范围 / 素材证据关系，见下 |
| related_units[] | 关联教学单元 ID |
| review | status=verified/pending/insufficient；reason 为具体范围和原因 |
| checks | fidelity/calculation/proof 各层实际产物的引用 |
| verification_model | 可选的独立物理状态模型 |

example/exercise 必须有 body、conditions、motivation、steps、conclusion。未取得完整题目先记录材料不足的 note，不猜补条件。review 的 verified 必须有当前 fidelity 记录；例题/练习还必须有 calculation 和 proof 记录。pending/insufficient 只允许校对稿。三个维度不能互相替代。

body/content/conclusion 支持（v0.3新增跨学科记号）：

- `{type: text, text: 普通文本}`：程序仅转义一次，常用 Unicode 数学符号规范化。
- `{type: math, latex: ...}`：受限数学 LaTeX，不含外层文档或 `$...$`。长公式主动写 aligned；程序不自动重排任意公式语义。
- `{type: chem, formula: "2 H2 + O2 -> 2 H2O"}`：使用mhchem排版化学式/反应式。
- `{type: quantity, value: "9.81", unit: "\\metre\\per\\second\\squared"}`：使用siunitx；JSON反斜杠由序列化器处理，YAML单引号可直接写。
- `{type: image, figure_id: fig1, caption: ...}`：引用本单元 embed 决策，不能直接引用任意路径。
- `{type: table, columns: [...], rows: [[...], ...]}`：矩形表，单元格用文本或 `{math: ...}`。
- `{type: sequence, variable: p, index: n, constant: "1/3", coefficient: "1/6", base: "2/5"}`：声明通项 c+k b^(n−1)，index 可 n/i/k。n=1直接取初值，避免0⁰。渲染与核验读取同一字段。
- `{type: coin_recurrence, coefficients: ["1/2","1/4","1/8"]}`：无连续三个正面模型。
- `{type: partition, direction: prefix, patterns: [T, HT, HHT]}`：硬币分类结构，可直接执行回归。

## 可执行最小单元

先 init/scaffold 新任务，再把以下自制结构示例保存为 unit.yaml 并 unit-put。section_id=c1 对应 scaffold 默认章节。该示例不冒充课程内容：

```yaml
id: demo
section_id: c1
type: example
title: 自制示例：一阶递推
origin: generated
answer_origin: generated
conditions: ["n为正整数"]
body:
  - type: text
    text: "已知a₁=1，aₙ₊₁=2aₙ+1，求通项。"
motivation: "寻找不动点−1，将递推转为等比数列。"
steps:
  - heading: 平移
    content:
      - type: math
        latex: |
          a_{n+1}+1=2(a_n+1).
conclusion:
  - type: math
    latex: |
      a_n=2^n-1.
pitfalls: ["初值对应第1项。"]
sources: []
evidence: []
related_units: []
review:
  status: pending
  reason: "结构示例；尚未记录来源、计算和证明复核。"
checks: {}
```

safe YAML 的 `|` 块保持反斜杠；JSON 文件由序列化器生成，勿手写错误转义。无效写入返回 saved=false，不覆盖原文。

## 来源与画面

`index JOB --start 1180 --end 1400` 查询真实字幕/帧 ID。模型证据包边界不限制查询或引用。不要手造 ID。

sources 对象：`{video_id: BV..., part: 1, start: 1078, end: 1386}`。必须匹配任务的视频和分P，满足 0≤start<end≤duration。只在同一教学单元内合并相邻（默认间隔≤2秒）/重叠范围，不跨不连续讲解。学生来源以标题、实际页码、P、时间和链接表达，内部 ID 留在报告。

v0.4百度任务由 baidu-init / 浏览器选择 / baidu-watch 或 baidu-import 建立 source.json；一个任务只绑定一个视频。video_id 使用任务实际分配的 baidu-分享ID-文件ID，内部 part=1 用于兼容同一内容协议，不代表B站分P。字幕/截图/单元必须匹配该来源和导入后的真实时长。学生稿显示网盘视频与本地时间；CSV记录文件名。分享 URL 仅打开分享页，不添加虚假的跳转时间。接收记录见 acquisition/baidu-receipt.json；登录状态、来源观察、媒体可解码和专业内容核验是分别成立的证据。只提取视频的任务不创建 handout.json 或 PDF。

evidence 对象：`{kind: frame, id: f..., relation: residual, reason: "口述已到总结，画面仍展示例3完整板书"}`。kind 为 frame/subtitle；relation 为 same_board、recap、residual、audio、external_reference。必须写明确语义原因，核查视频身份、素材原时间和文件。**画面无须落在本单元音频区间内**；这不是允许引用其他视频或非法时间。

figures 对象含 id、unit_id、frame_id、decision、reason、crop。crop=null 或 `[x,y,width,height]`，均为原图像素；超出原图时裁切器拒绝。decision：

| 值 | 用途 |
|---|---|
| embed | 教学图像确有新增信息，正文 image block 引用 |
| evidence_only | 转写/条件核对所需，正文已完整表达；说明信息保留方式 |
| omit_duplicate | 与其他证据重复，必须记录 covered_by 和覆盖理由 |

covered_by 应填实际帧/教学单元标识，审阅人核查信息是否完整。相似候选没有删除阈值，也不自动生成删除决策。完整原帧始终保留；细小正负号、下标或擦除前唯一式子需实际比较。

## 数学与来源复核

`verify-unit JOB ID --dimension calculation` 支持 sequence+verification_model：matrix 是完整物理状态转移矩阵，initial 表示第1步物理分布，targets 为目标状态下标。精确数用整数/分数字符串。独立递归枚举加权状态路径 n=1—10，再与最终 sequence 块比较；不能由待查闭式反推矩阵作“独立标准答案”。

硬币 calculation 枚举 H/T 长1—12，检查 p₃=7/8、p₄=13/16、递推和从n≥2严格递减。proof 另查 partition：前缀 T/HT/HHT 或后缀 T/TH/THH，包含互斥穷尽、T分隔与拼接边界结构证书；错误后缀 T/HT/HHT 返回反例。该证书只覆盖形式化分类块，正文单调性/适用条件另行复核。

一般证明/来源由宿主实际阅读材料后记录：

1. `unit-info JOB ID` 返回 target_digest、单元和证据文件哈希。
2. 保存复核 JSON，再 `review-unit JOB ID fidelity|calculation|proof FILE`。
3. 记录示例：

```json
{
  "target_digest": "取当前unit-info的值",
  "status": "passed",
  "method": "mathematical_review",
  "reviewer": "当前宿主模型（单次复查，非独立第二模型）",
  "coverage": "说明检查了哪些条件、等式、一般性论证与未覆盖项目",
  "evidence_files": [{"path":"materials/reference.pdf","sha256":"实际文件哈希"}],
  "findings": ["逐项观察与理由"]
}
```

人工方法仅 source_comparison、mathematical_review、counterexample_review；不得写成未执行的程序测试。verify-unit 自动保存真实输出。checks 引用 artifact、sha256、digest，产物含 target_digest、checker_version、dimension、status。程序核查内容摘要、检查器文件哈希、实际文件和所用证据哈希。它提供版本追溯，不是防伪签名。内容、条件、证明或裁切变更使旧记录失效，颜色/边距不改变数学摘要。

程序返回 needs_review 表示该形式化对象未被自动支持；不是通过。看到了有限样本正确，也不能升级任意证明为通过。

## 诊断、断点和报告

结构诊断带 code、unit_id、path、value、expected、evidence。优先修复指定字段；错误数学产物作为独立 issues 保留，不能用结构 valid 替代数学正确。

任务文件：source.json、materials/{subtitles,frames}.json、handout.json、units/、checks/、state.json、checkpoints.json、metrics.json、validation.json、diagnostics/、build/、deliverables/。阶段输出按哈希恢复，单元按次保存；PDF/验证断点保留内容与下一步动作。config.json 示例：

```json
{"repair_budgets":{"network":2,"structure":3,"source":3,"render":3}}
```

预算为连续失败上限，不是自动承诺重试次数。成功阶段清零相应类别；确定性错误停止并保留 diagnostics，修复原因后可由宿主明确调整预算。等待登录不消耗轮询预算。异常退出的 .lock 仅在确认旧进程结束后移除。

学生 PDF 不打印核验表/内部字段；独立 processing-report.json 保存覆盖、疑点、截图决策、运行指纹、PDF审计和可观察指标。visual_review 初始 pending；实际看图后另存绑定最终 PDF 哈希的视觉记录。不要把模型调用/人工次数缺测填写为零。

## v0.3学科范围

文档根可加subject说明学科，并以typography.math_font选择stix2或termes。通用结构适用于理工与经管课程；计算/证明维度在其他学科分别覆盖核算与推导/适用条件。现有自动路径枚举只处理已实现概率模型，其他学科使用实际专业复查记录。字体与符号见academic-notation.md。
