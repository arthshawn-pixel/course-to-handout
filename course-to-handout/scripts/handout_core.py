"""Persistent jobs, evidence validation and safe content model (stdlib only)."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode

VERSION = "0.4.0"


class HandoutError(Exception):
    pass


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise HandoutError(f"无法读取 JSON: {Path(path).name}: {exc.__class__.__name__}") from exc


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def within(root, relative):
    root = Path(root).resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise HandoutError("资源路径超出任务目录")
    return candidate


@contextlib.contextmanager
def locked(job):
    path = Path(job) / ".lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise HandoutError("任务正在执行；若上次进程意外退出，先确认进程已结束，再删除任务目录 .lock") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def stage(job, name, inputs, action):
    """An output modified outside the program invalidates its cache too."""
    job = Path(job)
    lookup_started=time.monotonic()
    state_path = job / "state.json"
    state = read_json(state_path)
    key = digest({"version": VERSION, "inputs": inputs})
    previous = state["stages"].get(name, {})
    if previous.get("key") == key and previous.get("status") == "done":
        if all(within(job, p).is_file() and file_hash(within(job, p)) == h
               for p, h in previous.get("outputs", {}).items()):
            from handout_workflow import metric
            metric(job,'stage',stage=name,status='done',cached=True,wall_seconds=time.monotonic()-lookup_started)
            return {"stage": name, "cached": True}
    from handout_workflow import guard_budget,metric,checkpoint,failure,category
    guard_budget(job,name)
    started=time.monotonic()
    state["stages"][name] = {"key": key, "status": "running", "started": time.time()}
    write_json(state_path, state)
    try:
        outputs = action()
        hashes = {str(Path(p).relative_to(job).as_posix()): file_hash(p) for p in outputs}
    except Exception as exc:
        state = read_json(state_path)
        state["stages"][name].update(status="failed", error_type=type(exc).__name__)
        write_json(state_path, state)
        failure(job,name,exc)
        metric(job,'stage',stage=name,status='failed',cached=False,wall_seconds=time.monotonic()-started)
        raise
    state = read_json(state_path)
    state["stages"][name].update(status="done", outputs=hashes, finished=time.time())
    state.setdefault('repair_failures',{})[category(name)]=0
    write_json(state_path, state)
    metric(job,'stage',stage=name,status='done',cached=False,wall_seconds=time.monotonic()-started)
    checkpoint(job,name,list(hashes),'复核当前阶段输入后继续下游阶段')
    return {"stage": name, "cached": False}


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def interval(start, end, duration):
    return number(start) and number(end) and 0 <= start < end <= duration + .05


def stamp(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def public_url(url):
    """Never retain credentials, fragments, arbitrary tracking/session queries."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise HandoutError("来源链接必须是无凭证的 HTTPS 链接")
    keep = {k: v[0] for k, v in parse_qs(parts.query).items() if k in ("p", "t")}
    return urlunsplit(("https", parts.hostname, parts.path, urlencode(keep), ""))


def source_link(manifest, start):
    if not manifest.get("url"):
        return ""
    parts = urlsplit(public_url(manifest["url"]))
    if manifest.get('provider')=='baidu':return urlunsplit((parts.scheme,parts.netloc,parts.path,'',''))
    query = parse_qs(parts.query)
    query.update(p=[str(manifest["part"])], t=[str(int(start))])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ""))


# Formula input is a restricted math language, never arbitrary TeX.
MATH_COMMANDS = set("frac dfrac tfrac sqrt left right cdot times div pm mp le leq ge geq ne neq approx equiv sim in notin subset subseteq cup cap emptyset forall exists to mapsto implies iff infty sum prod int iint lim sin cos tan cot arcsin arccos arctan log ln exp min max sup inf det gcd alpha beta gamma delta epsilon varepsilon theta lambda mu nu xi pi rho sigma tau phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega mathbb mathcal mathrm mathbf mathit mathsf boldsymbol text operatorname overline underline vec hat bar dot ddot binom dbinom begin end quad qquad langle rangle lvert rvert lVert rVert vert Vert mid big Big bigg Bigg limits nolimits partial nabla ell degree angle perp parallel colon dots ldots cdots vdots ddots underbrace overbrace underset overset substack cases matrix pmatrix bmatrix vmatrix Vmatrix aligned split gather gathered array hline sum int bmod mod pmod sin cos tan sec csc cfrac displaystyle scriptscriptstyle scriptstyle textstyle emptyset setminus land lor neg lbrace rbrace backslash top bot ast circ bullet prime mathop mathbin mathrel mathopen mathclose mathpunct mathinner mathnormal ensuremath".split())
ENVIRONMENTS = {"cases", "matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "aligned", "gathered", "array", "split"}
MATH_COMMANDS.update('succeq preceq prec succ widehat widetilde tilde acute grave'.split())
MATH_COMMANDS.update('zeta eta iota kappa upsilon omicron Upsilon varepsilon vartheta varpi varrho varsigma varkappa varnothing'.split())
MATH_COMMANDS.update("rightarrow leftarrow Rightarrow Leftarrow Longrightarrow Longleftarrow Leftrightarrow Longleftrightarrow leqslant geqslant nleq ngeq because therefore".split())
MATH_COMMANDS.update("iiint iiiint oint oiint oiiint hbar hslash Re Im dagger ddagger lceil rceil lfloor rfloor otimes oplus odot ominus oslash bigotimes bigoplus cong propto simeq ll gg nabla wp aleph beth complement not approx asymp subsetneq supset supseteq uparrow downarrow rightleftharpoons longrightarrow longleftarrow symbf symbfit symit symup symbb symcal symscr symfrak symbfsf mathscr mathfrak mathring arg ker dim Pr ce qty unit num SI si ang per squared cubed metre meter second ampere kelvin mole candela kilogram gram newton joule watt pascal hertz coulomb volt ohm farad tesla weber henry siemens lumen lux becquerel gray sievert katal degreeCelsius radian steradian percent electronvolt litre liter minute hour day decibel micro nano pico milli centi deci kilo mega giga tera femto atto square cubic reciprocal atomicmassunit angstrom bohr clight planck reducedplanck".split())


def validate_math(formula):
    if not isinstance(formula, str) or not formula.strip() or len(formula) > 6000:
        raise HandoutError("公式为空或超过 6000 字符")
    if any(x in formula for x in ("%", "#", "$", "^^")) or any(ord(c) < 32 and c not in "\n\t" for c in formula):
        raise HandoutError("公式不能包含注释、参数或数学模式分隔符")
    for match in re.finditer(r"\\([A-Za-z]+|.)", formula):
        command = match.group(1)
        if command not in MATH_COMMANDS and command not in set("{} ,;:!|\\_"):
            raise HandoutError(f"不支持的公式命令: \\{command}")
    depth = 0
    for token in re.findall(r"\\.|[{}]", formula):
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
        if depth < 0:
            raise HandoutError("公式花括号不匹配")
    if depth:
        raise HandoutError("公式花括号不匹配")
    stack = []
    for action, env in re.findall(r"\\(begin|end)\s*\{([^{}]+)\}", formula):
        if env not in ENVIRONMENTS:
            raise HandoutError("不支持的公式环境")
        if action == "begin":
            stack.append(env)
        elif not stack or stack.pop() != env:
            raise HandoutError("公式环境不匹配")
    if stack:
        raise HandoutError("公式环境未结束")


def parse_subtitles(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
        body = raw.get("body", []) if isinstance(raw, dict) else raw
        items = [{"start": x.get("from", x.get("start")), "end": x.get("to", x.get("end")),
                  "text": x.get("content", x.get("text", ""))} for x in body]
    else:
        items = []
        pattern = r"(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s*-->\s*(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})[^\n]*\n([^\n]+(?:\n(?!\s*\n)[^\n]+)*)"
        def seconds(v):
            nums = [float(n) for n in v.replace(",", ".").split(":")]
            return sum(n * 60 ** i for i, n in enumerate(reversed(nums)))
        for match in re.finditer(pattern, text):
            items.append({"start": seconds(match[1]), "end": seconds(match[2]),
                          "text": re.sub(r"<[^>]+>", "", match[3]).strip()})
    if not items:
        raise HandoutError("未解析到字幕；支持 UTF-8 SRT、VTT、B 站 JSON 或时间戳数组")
    items.sort(key=lambda x: x["start"] if number(x["start"]) else -1)
    for i, item in enumerate(items):
        if not interval(item["start"], item["end"], 10 ** 9) or not isinstance(item["text"], str) or not item["text"].strip():
            raise HandoutError("字幕时间或正文无效")
        item["id"] = f"s{i + 1:05}"
    return items


def validate_document(doc, manifest, subtitles, frames, root):
    """Return structural problems and review issues separately; no accuracy scores."""
    if isinstance(doc,dict) and doc.get('schema_version')==2:
        from handout_v2 import validate_v2
        return validate_v2(doc,manifest,subtitles,frames,root)
    errors, issues = [], []
    def check(condition, message):
        if not condition:
            errors.append(message)
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    def texts(value):
        return isinstance(value, list) and all(text(x) for x in value)
    if not isinstance(doc, dict):
        return {"valid": False, "errors": ["讲义必须为对象"], "issues": []}
    check(doc.get("schema_version") == 1, "schema_version 必须为 1")
    check(text(doc.get("title")), "缺少标题")
    check(text(doc.get("level")), "缺少课程阶段")
    check(texts(doc.get("prerequisites")), "prerequisites 必须是文本数组")
    check(text(doc.get("coverage")), "必须说明素材覆盖范围")
    sections = doc.get("sections", [])
    units = doc.get("units", [])
    if not isinstance(sections, list) or not isinstance(units, list) or not units:
        return {"valid": False, "errors": errors + ["章节/内容单元无效或为空"], "issues": []}
    sid, uid = set(), set()
    ranges = {}
    duration = manifest["duration"]
    smap = {x["id"]: x for x in subtitles}
    fmap = {x["id"]: x for x in frames}
    for section in sections:
        if not isinstance(section, dict):
            errors.append("章节必须为对象")
            continue
        ident = section.get("id", "")
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", ident):
            errors.append("章节 ID 无效")
            continue
        check(ident not in sid, f"重复章节 {ident}")
        sid.add(ident)
        check(text(section.get("title")), f"{ident}: 缺少章节标题")
        check(section.get("origin") in ("model", "platform", "human"), f"{ident}: 缺少分段来源")
        if interval(section.get("start"), section.get("end"), duration):
            ranges[ident] = (section["start"], section["end"])
        else:
            errors.append(f"{ident}: 章节时间越界")
    def blocks(items, label):
        if not isinstance(items, list):
            errors.append(f"{label}: 内容必须为 block 数组")
            return
        for b in items:
            if not isinstance(b, dict):
                errors.append(f"{label}: block 必须是对象")
                continue
            if b.get("type") == "text":
                check(text(b.get("text")), f"{label}: 空文本")
            elif b.get("type") == "math":
                try:
                    validate_math(b.get("latex"))
                except HandoutError as exc:
                    errors.append(f"{label}: {exc}")
            elif b.get("type") == "image":
                frame = fmap.get(b.get("frame_id")) if isinstance(b.get("frame_id"), str) else None
                check(frame is not None, f"{label}: 图片引用不存在")
                if frame:
                    try:
                        p = within(root, frame["path"])
                        check(p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg"), f"{label}: 图片文件无效")
                    except HandoutError as exc:
                        errors.append(str(exc))
            else:
                errors.append(f"{label}: 不支持的 block 类型")
    for u in units:
        if not isinstance(u, dict):
            errors.append("内容单元必须为对象")
            continue
        ident = u.get("id", "")
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", ident):
            errors.append("内容 ID 无效")
            continue
        check(ident not in uid, f"重复内容 ID {ident}")
        uid.add(ident)
        section_id = u.get("section_id")
        check(isinstance(section_id, str) and section_id in sid, f"{ident}: 章节不存在")
        check(u.get("type") in ("definition", "theorem", "example", "note", "exercise"), f"{ident}: 单元类型无效")
        origin = u.get("origin")
        check(origin in ("course", "ai_supplement", "generated", "comment", "external"), f"{ident}: 来源类别无效")
        if u.get("type") == "exercise":
            check(origin == "generated", f"{ident}: 首版自测必须明确标记 generated")
        check(text(u.get("title")), f"{ident}: 标题为空")
        for key in ("conditions", "pitfalls"):
            check(texts(u.get(key)), f"{ident}: {key} 必须为文本数组")
        check(isinstance(u.get("raw_recognition"), list), f"{ident}: raw_recognition 必须保留数组（可以为空）")
        check(type(u.get("wide", False)) is bool, f"{ident}: wide 必须为布尔值")
        for key in ("body", "conclusion"):
            blocks(u.get(key), f"{ident}.{key}")
        if u.get("type") in ("example", "exercise"):
            check(bool(u.get("body")), f"{ident}: 缺少完整题干")
            check(text(u.get("motivation")), f"{ident}: 缺少方法动机")
            check(bool(u.get("steps")), f"{ident}: 缺少分步解答")
            check(bool(u.get("conclusion")), f"{ident}: 缺少结论")
        if u.get("type") in ("theorem", "example"):
            check(bool(u.get("conditions")), f"{ident}: 必须保存适用条件")
            check(bool(u.get("conclusion")), f"{ident}: 必须保存结论")
        steps = u.get("steps", [])
        if not isinstance(steps, list):
            errors.append(f"{ident}: steps 必须为数组")
            steps = []
        for step in steps:
            if not isinstance(step, dict):
                errors.append(f"{ident}: step 无效")
                continue
            blocks(step.get("content"), ident + ".step")
            check(text(step.get("basis")), f"{ident}: 步骤缺少依据")
            check(step.get("origin") in ("course", "ai_supplement", "generated", "comment", "external"), f"{ident}: 步骤必须标明来源")
        refs = u.get("sources", [])
        if not isinstance(refs, list):
            errors.append(f"{ident}: sources 必须为数组")
            refs = []
        if origin == "course":
            check(bool(refs), f"{ident}: 原课内容缺少来源")
            check(text(u.get("original_text")), f"{ident}: 缺少原始材料摘录")
        if origin in ("ai_supplement", "generated"):
            check(bool(u.get("related_units")), f"{ident}: 补充或自测须关联原课内容")
        if origin in ("comment", "external"):
            try:
                public_url(u.get("external_url", ""))
            except HandoutError:
                errors.append(f"{ident}: 外部内容缺少有效来源链接")
        for ref in refs:
            if not isinstance(ref, dict):
                errors.append(f"{ident}: 来源必须为对象")
                continue
            check(ref.get("video_id") == manifest["video_id"] and ref.get("part") == manifest["part"], f"{ident}: 来源视频或分 P 不匹配")
            a, b = ref.get("start"), ref.get("end")
            if not interval(a, b, duration):
                errors.append(f"{ident}: 来源时间越界")
                continue
            sec_range = ranges.get(section_id) if isinstance(section_id, str) else None
            check(sec_range is not None and sec_range[0] <= a < b <= sec_range[1] + .05, f"{ident}: 来源不在章节时间内")
            subids, frameids = ref.get("subtitle_ids", []), ref.get("frame_ids", [])
            if not isinstance(subids, list) or not isinstance(frameids, list):
                errors.append(f"{ident}: 证据 ID 必须为数组")
                continue
            check(bool(subids or frameids), f"{ident}: 来源没有证据")
            for item in subids:
                evidence = smap.get(item) if isinstance(item, str) else None
                check(evidence is not None, f"{ident}: 字幕 ID 不存在")
                if evidence:
                    check(evidence["start"] < b and evidence["end"] > a, f"{ident}: 字幕与来源时段不重叠")
            for item in frameids:
                evidence = fmap.get(item) if isinstance(item, str) else None
                check(evidence is not None, f"{ident}: 截图 ID 不存在")
                if evidence:
                    check(a - .05 <= evidence["time"] <= b + .05, f"{ident}: 截图与来源时段不重叠")
        displayed = [b.get("frame_id") for group in [u.get("body", []), u.get("conclusion", []),
                     *[s.get("content", []) for s in steps if isinstance(s, dict)]]
                     if isinstance(group, list) for b in group if isinstance(b, dict) and b.get("type") == "image"]
        source_frames = [f for r in refs if isinstance(r, dict) and isinstance(r.get("frame_ids", []), list) for f in r.get("frame_ids", [])]
        check(all(f in source_frames for f in displayed), f"{ident}: 正文截图必须包含在该单元的来源记录中")
        review = u.get("review", {})
        if not isinstance(review, dict):
            review = {}
        check(review.get("status") in ("verified", "pending", "insufficient"), f"{ident}: 核对状态无效")
        check(text(review.get("reason")), f"{ident}: 核对状态必须说明原因")
        if review.get("status") == "verified":
            check(text(review.get("method")) and text(review.get("reviewer")), f"{ident}: 已核对必须记录方法与核对者")
            check(bool(review.get("evidence_checked")) and texts(review.get("evidence_checked")), f"{ident}: 已核对必须记录实际对照的证据")
        else:
            issues.append({"unit_id": ident, "status": review.get("status"), "reason": review.get("reason", "未核对")})
    for u in units:
        if not isinstance(u, dict):
            continue
        related = u.get("related_units", [])
        if not isinstance(related, list):
            errors.append(f"{u.get('id')}: related_units 必须是数组")
        else:
            for ident in related:
                check(isinstance(ident, str) and ident in uid and ident != u.get("id"), f"{u.get('id')}: 关联单元不存在或自引用")
    # Chronology is checked within ordinary course content; exercises live at the end.
    starts = [u["sources"][0]["start"] for u in units if isinstance(u, dict) and u.get("origin") == "course"
              and isinstance(u.get("sources"), list) and u["sources"] and isinstance(u["sources"][0], dict)
              and number(u["sources"][0].get("start"))]
    check(starts == sorted(starts), "原课内容必须沿视频顺序排列")
    return {"valid": not errors, "errors": errors, "issues": issues,
            "release_ready": not errors and not issues,
            "notice": "结构通过不代表数学正确；已核对状态取决于实际来源对照记录。"}
