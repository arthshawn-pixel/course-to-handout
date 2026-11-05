# v0.4 运行与交付

本项目是通用 Agent Skill + Python CLI + XeTeX 固定模板，并提供 WorkBuddy 上传包。理工与经管课程的语义整理使用宿主模型，不需要额外模型 API key。v0.4保留B站、字幕交接和学科字体，新增百度网盘的宿主浏览器/官方客户端下载流程；离线测试不代表用户账户内端到端成功。

## Windows x64 环境

上传 WorkBuddy ZIP 到客户端技能入口。上传包含平台展示字段、脚本、模板、参考文档和字体，不含课程视频、开发测试或运行缓存。实际客户端导入须以当前 WorkBuddy 结果为准。

电脑需要 Python 3.10+。在可写的课程工作目录运行，Skill 路径指向导入/解压目录：

```powershell
& "Skill所在目录/scripts/setup_windows.ps1" -RuntimePath "D:/lessons/handout-runtime"
```

脚本在独立 .venv 安装固定版本 yt-dlp、imageio-ffmpeg、Pillow、pypdf、PyYAML；下载校验 Tectonic0.17.0，或用 -CompilerExe 指定已有编译器。复用依赖与编译缓存，不修改全局 Python/PATH/系统执行策略。需要进程级执行策略时只在该次 PowerShell 进程指定。首次下载失败时保留目录和诊断，确认网络后续作，勿无限安装。

runtime.json 含 python、compiler、tex_cache、engine、fonts、root。后续课程使用同一个环境：

```powershell
$runtimeConfig = Get-Content "D:/lessons/handout-runtime/runtime.json" -Raw | ConvertFrom-Json
$env:HANDOUT_TEX = $runtimeConfig.compiler
$env:HANDOUT_RUNTIME = $runtimeConfig.root
$env:TECTONIC_CACHE_DIR = $runtimeConfig.tex_cache
& $runtimeConfig.python "Skill所在目录/scripts/lecture.py" preflight $runtimeConfig.root --engine tectonic
```

preflight 实际生成2秒带音视频、抽图、解析字幕并编译含中文/英文/数学/长知识框/图注的小 PDF。capabilities.json 记录系统、架构、Python、依赖版本、编译器/字体/脚本/模板指纹；指纹与小样 PDF 哈希相符时复用。初次预热默认允许900秒编译（HANDOUT_WARMUP_TIMEOUT 可调），正式课程默认300秒（HANDOUT_TEX_TIMEOUT 可调）。预热超时与正文编译分开记录；超时保留缓存。无预装 TeX bundle 的首轮需要网络，不能据开发机热缓存推断另一台电脑的冷启动速度。

核心 JSON/字幕/索引校验可用标准库；YAML、裁切、PDF审计使用上述依赖。FFmpeg可由固定 imageio-ffmpeg 提供；HANDOUT_FFMPEG 可指定已有程序。已有 TeX Live/MiKTeX 可用 --engine xelatex，至少需 fontspec、xeCJK、unicode-math、tcolorbox、longtable、needspace 等。包内包含思源宋体Regular、TeX Gyre Termes正文及Math、STIX Two Math（许可随包），默认数学字体为STIX Two Math；--fonts windows使用本机SimSun，不重新分发系统字体。

doctor 只检查依赖/路径，不代表媒体/排版实测通过，也不代表宿主有浏览器或ASR。preflight 后仍需看小样PDF；浏览器和转写能力由宿主检查。

## 新课程与编辑

```powershell
python scripts/lecture.py init D:/lessons/job1 --video D:/lessons/course.mp4 --title 课程标题 --level 高中
python scripts/lecture.py subtitles D:/lessons/job1 D:/lessons/course.srt --origin platform
python scripts/lecture.py frames D:/lessons/job1 --interval 60
python scripts/lecture.py frames D:/lessons/job1 --times 125 140 165
python scripts/lecture.py prepare D:/lessons/job1 --chunk 600
python scripts/lecture.py scaffold D:/lessons/job1
python scripts/lecture.py contract
python scripts/lecture.py index D:/lessons/job1 --start 120 --end 180
# 宿主读材料、查看图片，逐单元写JSON/YAML并按协议核验
python scripts/lecture.py unit-put D:/lessons/job1 D:/lessons/unit.yaml
python scripts/lecture.py check D:/lessons/job1
python scripts/lecture.py render D:/lessons/job1 --engine tectonic --draft
python scripts/lecture.py render D:/lessons/job1 --engine tectonic --draft --mode writing
python scripts/lecture.py resume D:/lessons/job1
```

实际使用上方 runtimeConfig.python 调用，不必另外安装全局依赖。CLI不会自动凭标题写出内容，需宿主按照 SKILL.md 分单元整理。

B站链接用 init --url HTTPS_URL --part N，再fetch。DASH分离音视频分别获取后合并；浏览器登录不自动传给下载器。subtitles-status明确检查公开字幕状态，browser-subtitles核对导出包视频/分P/CID与时间。详细见 browser-handoff.md。平台字幕/ASR均不可用时可继续板书能覆盖的部分，并如实标注不足。

百度分享用 baidu-init / baidu-plan，不使用 B站 init --url。用户自行登录/验证码，Agent 通过宿主官方浏览器工具观察、选择和下载，再 baidu-watch / baidu-import。仅下载用 --intent video_only，不要求 TeX 排版预热。完整命令、观察结构和停止条件见[百度浏览器流程](baidu-browser.md)。这些命令不控制 UI；宿主必须实际提供可验证 URL、官方点击和本地文件路径的能力。缺失时保存中断，不读取凭证或猜私有接口。

v2 单栏 reading / writing，margin18—22mm、blue/slate。学生PDF、语义来源CSV、处理报告分别生成。原课题源继承课件时注明“课件标注”，未外查不冒充核实真题出处。校对稿因来源未核全而保留标记；开发样本正确不代表整门视频自动识别质量已验收。

只改版式直接render，不再fetch/audio/frames/prepare。渲染缓存绑定最终内容、scripts下所有Python/JS、字符处理、模板、字体、编译器、Python依赖和图像/选项。单个字符改动触发重新渲染，数学记录按内容摘要单独失效。阶段完成输出经哈希核查，损坏即重做该阶段。网络/结构/来源/排版预算与诊断见内容协议。

## 开发复现与范围

源码发行含 tests、tools；上传包不含。执行：

```powershell
python -m unittest discover -s tests -p "test_*.py"
node --test tests/browser_subtitles.test.js
python tools/package_skill.py OUTPUT.zip
```

test_v2 覆盖跨包/残留板书引用、错误视频时间、物理路径枚举、硬币错误分类、证明记录过期/缺失、YAML、截图决策、预算与恢复。test_pipeline 保留 v1 采集/安全/缓存兼容测试。reference_course/build_reference_sample 为开发回归夹具，示范将用户修订稿重建为规范数据；不是运行新课程必须改写的脚本。模型使用 scaffold/unit-put 固定接口。

范围：理工与经管类课程整理、单个B站分P、本地视频、百度分享单视频的宿主下载交接、现成字幕/宿主转写输出。学科符号按academic-notation.md排版；专业内容逐学科复核。未捆绑ASR/OCR模型、评论抓取或MCP服务。双栏按v0.2改版要求后续处理。WorkBuddy实际导入/真实字幕导出、新电脑冷启动和百度真实分享的官方下载仍需各自实际验证；开发回归不会把这些标记为已通过。

## 跨Agent安装

使用整个通用course-to-handout文件夹，不只复制SKILL.md。Claude Code项目目录为.claude/skills/course-to-handout，调用/course-to-handout；Codex项目目录为.agents/skills/course-to-handout，用$course-to-handout或技能选择器调用。WorkBuddy使用专用ZIP。agents/openai.yaml仅为Codex展示元数据，其他宿主使用通用SKILL.md及资源即可。浏览器、登录和图像工具由各宿主提供，安装Skill不会自动授予这些能力。

程序路径以Skill目录为准，运行环境与任务目录使用绝对路径。Windows x64安装脚本可直接复用；macOS/Linux可用Python3.10+、requirements-media.txt、FFmpeg和Tectonic/XeLaTeX手工配置，跨系统冷启动尚未实测。字体随包，不依赖系统字体安装。首次运行notation-sample NEW_JOB确认学科符号；样例缺字审计会失败，仍须看PDF图像。

[Codex官方](https://learn.chatgpt.com/docs/build-skills)、[Claude Code官方](https://code.claude.com/docs/en/skills)。
