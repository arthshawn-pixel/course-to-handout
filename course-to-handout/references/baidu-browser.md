# 百度网盘：宿主操作浏览器，用户登录

用户粘贴分享链接及提取码后，由 Agent 完成以下交接。用户只负责账号登录、扫码与验证码；不要要求用户执行这些 CLI 命令。Python 没有内置浏览器，也不继承登录态，负责状态、下载监控和本地视频校验。使用宿主正式支持的浏览器/电脑工具，先读其说明；不假设 WorkBuddy、Claude Code、Codex 有相同工具或下载能力。

## 入口与能力

接受 `https://pan.baidu.com/s/1...`、`/share/init?surl=...` 或包含链接和“提取码”的分享文本。一个任务只处理一个视频；多个分享分别建任务。JOB 必须是独立绝对路径。

```text
python scripts/lecture.py baidu-init JOB --share "完整分享文本" --title "课程标题" --level "课程阶段"
python scripts/lecture.py baidu-plan JOB
```

仅验证视频提取时加 `--intent video_only`，取得视频后停止，不生成讲义或 PDF。`fetch JOB` 对百度任务只返回浏览器计划。已有任务先 `resume JOB` / `baidu-status JOB`；不要重复新建。缺提取码时可 `baidu-code JOB 四位提取码`。提取码不是账号密码，只存在任务的 private-baidu-request.json，plan 会按需提供；任务目录不得加入发行包或公开仓库。

宿主至少需要：可靠读取当前网页 URL、观察分享文件列表、点击官方的下载入口，以及设置下载目录或取得实际下载路径。UI 定位依据新截图/页面结构，工具名和控件位置以当前宿主说明为准。桌面官方客户端是网页要求时的可选路径，不默认静默安装、不自动购买会员。没有可靠的下载能力就保存 tool_unavailable，不能宣称 Skill 本身提供了该能力。

## 页面与用户交接

1. 告知将访问百度网盘，打开 plan.browser.official_url；实际核对当前 URL 和分享身份。不是读取链接字符串后就算打开成功。
2. 需要登录或验证时记录 waiting_login / waiting_verification，向用户说明正在等待哪个官方页面/客户端。让用户亲自完成，收到完成消息后重新观察。不要填写账号密码、自动扫码、解验证码、导出 Cookie 或轮询登录。已登录的会话可以复用，但仍验证资源可读。
3. 提取码可由 Agent 使用用户给定值输入官方分享页；不知道则等待用户提供。不要猜码。用户说“已登录”不构成 files_visible 的证据。
4. 读取实际文件列表。文件夹可先在浏览器中展开；只记录当前目标范围。用户已指定文件就选它，否则唯一视频可自动选，多视频先询问目标。不要默认下载整个目录。

用 `baidu-record JOB OBSERVATION.json` 保存每次实际观察。以下是结构示例，值须替换为本次工具结果，不能照抄当作验收证据：

```json
{
  "event": "files_visible",
  "observed_url": "https://pan.baidu.com/s/1EXAMPLEshare",
  "files": [{"id":"video-1","name":"课程01.mp4","bytes":null,"is_dir":false}],
  "evidence": {"kind":"browser_snapshot","tool":"本次实际工具名","reference":"本次实际页面或截图结果引用"}
}
```

bytes 仅在界面提供精确字节数时写整数，只有 MB 约数就填 null。id 优先页面稳定 ID，没有可省略，由程序生成。禁止填写下载签名、Cookie、账号或任意网络返回体。登录观察同结构但 event 为 waiting_login，省略 files；支持该分享页和官方 passport.baidu.com / wappass.baidu.com 登录页，记录时剥离登录查询参数。

唯一视频自动进入 ready_to_download；多视频用 `baidu-select JOB FILE_ID`。任务将文件 ID、名字、精确大小（如有）与来源绑定，plan 返回该文件专用 download_directory。

## 官方下载与本地接收

优先在官方网页下载所选视频，保存到 plan 给出的目录；网页必须用官方客户端时，由宿主按当前 UI 转交已安装的客户端。若客户端需要登录，仍交用户操作。网页及客户端能否下载、是否需要额外权限，以实际页面为准。不要通过第三方解析站、私有下载接口或读取浏览器凭证获取直链。

实际观察到所选文件的下载任务建立后记录：

```json
{
  "event":"download_started",
  "observed_url":"https://pan.baidu.com/s/1EXAMPLEshare",
  "method":"official_client",
  "evidence":{"kind":"client_snapshot","tool":"本次实际工具名","reference":"已核对的分享页及所选文件下载任务观察引用"}
}
```

method 取 browser_download 或 official_client。客户端没有地址栏时，observed_url 仍来自已实际核对的官方分享页，evidence 同时指向分享页和所选文件的客户端任务；不要把期望 URL 冒充观察结果。点击失败或仅出现安装提示，不能记录 download_started。

```text
python scripts/lecture.py baidu-watch JOB --timeout 30
python scripts/lecture.py baidu-status JOB
```

每次 watch 最长 60 秒；分轮检查并告知进度，用户取消即记录 paused。临时扩展名、选择前已存在且未变化的文件、同名多候选、空文件、大小不符均不能进入 acquired。文件需要至少两次稳定观察（默认 3 秒）。

精确大小未知时，还须实际看到所选文件在官方下载界面完成，记录 event=download_completed（使用同样的 observed_url 与真实工具证据，省略 method）。用户一句“完成”不能伪造成客户端观察；可改为明确确认完整本地文件的导入。不能把静止的半成品当成下载完成。

若官方下载器无法改保存目录，但宿主能确认实际文件路径，直接导入该文件：

```text
python scripts/lecture.py baidu-import JOB "完整本地文件路径"
```

导入校验所选名字/精确大小、关联临时文件、视频轨、时长、首帧实际解码和 SHA256；文件在校验中变化会失败。外部文件复制进任务，原文件保留。若文件被改名、没有页面选择记录或无法观察完成状态，先由用户明确确认该完整文件来自该分享，再加 `--source-confirmed`。该参数是对实际确认的记录，不是绕过问题的重试开关。

成功保存 source.json、acquisition/baidu-receipt.json 和断点。receipt 明确记录来源依据及检查范围：首帧解码不是全片逐帧验收，SHA256 只校验本地文件一致性，不证明网站来源。页面来源依赖宿主实际观察/用户确认，脚本无法独立证明这些 UI 记录真实性。恢复会检查文件和 receipt 哈希；文件变更不会沿用旧完成状态。

intent=video_only 时到此停止。intent=handout 时沿用字幕→音频转写（必要时）→关键帧→单元整理流程。百度分享不自动提供课程逐字字幕，不能把平台 AI 总结当逐字稿。讲义的时间是本地视频时间，分享 URL 只指向分享页，不声称能一键跳到该秒。

## 中断与工具限制

工具不存在、当前 URL 无法验证或工具明确停止时，停止受影响的浏览器操作并记录真实原因；不得重置控制工具、私接 CDP/调试端口来绕过停止。

```json
{
  "event":"tool_unavailable",
  "reason":"cannot_verify_url",
  "evidence":{"kind":"browser_snapshot","tool":"实际失败的工具名","reference":"实际失败结果引用"}
}
```

此事件无需 observed_url，因为工具未能确认它。reason 可用 cannot_verify_url / no_browser_tool / browser_tool_stopped / client_unavailable / other_tool_error。保留任务等待工具恢复；这和百度账号是否登录分别处理。恢复可用工具后重新观察同一分享，不重做已校验的视频。

用户明确暂停用 event=paused、reason=user_paused，证据为该用户消息；收到明确继续再记 event=resumed、kind=user_message。达到 config.json 的 source 修复预算则先排查诊断，不自动反复导入失败文件。

本版自动测试覆盖模拟页面观察与真实自制媒体的接收/解码。真实百度分享的官方浏览器下载仍须单独验收；安装 Skill 不等于完成该网站验收。
