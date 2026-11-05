"""Fixed XeTeX template; all user text escaped and formula commands constrained."""
from __future__ import annotations

import csv
import copy
import os
import re
import shutil
import subprocess
from pathlib import Path

from handout_core import HandoutError, read_json, write_json, within, file_hash, stamp, source_link, validate_document, stage

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = {"course": "原课整理", "ai_supplement": "AI 补充", "generated": "生成自测", "comment": "评论补充", "external": "外部参考"}
TYPES = {"definition": "定义", "theorem": "定理", "example": "例题", "note": "说明", "exercise": "自测"}


def escape(value):
    mapping = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&",
               "#": r"\#", "%": r"\%", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    mapping.update({"′": r"\ensuremath{{}^{\prime}}", "″": r"\ensuremath{{}^{\prime\prime}}",
                    "∞": r"\ensuremath{\infty}", "≤": r"\ensuremath{\leq}", "≥": r"\ensuremath{\geq}"})
    mapping.update({c: r"\ensuremath{{}_" + str(i) + "}" for i, c in enumerate("₀₁₂₃₄₅₆₇₈₉")})
    mapping.update({c: r"\ensuremath{{}^" + str(i) + "}" for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")})
    return "".join(mapping.get(c, c) for c in str(value)).replace("\n", "\n\n")


def engine_path(engine):
    executable = os.environ.get("HANDOUT_TEX") or shutil.which(engine)
    if not executable:
        raise HandoutError(f"缺少 {engine} 编译器；安装后配置 PATH 或 HANDOUT_TEX")
    return executable


def load_materials(job):
    return (read_json(job / "source.json"), read_json(job / "materials/subtitles.json"), read_json(job / "materials/frames.json"))


def render(job, layout="single", draft=False, engine="xelatex", fonts="sourcehan",mode='reading',accent='blue',margin=20):
    job = Path(job).resolve()
    doc = read_json(job / "handout.json")
    if doc.get('schema_version')==2:
        from handout_student import render_student
        return render_student(job,layout,draft,engine,fonts,mode,accent,margin)
    manifest, subtitles, frames = load_materials(job)
    report = validate_document(doc, manifest, subtitles, frames, job)
    write_json(job / "validation.json", report)
    if not report["valid"]:
        raise HandoutError("结构校验失败，见 validation.json；没有编译")
    if report["issues"] and not draft:
        raise HandoutError("存在待核对内容，只能使用 --draft 导出明确标记的草稿")
    executable = engine_path(engine)
    build = job / "build" / layout
    build.mkdir(parents=True, exist_ok=True)
    template = ROOT / "templates/lecture.tex"
    bundled_font = ROOT / "assets/fonts/SourceHanSerifSC-Regular.otf"
    figures = {f["id"]: f for f in frames}
    referenced = {b["frame_id"] for u in doc["units"] for blocks in
                  [u["body"], u["conclusion"], *[s["content"] for s in u.get("steps", [])]]
                  for b in blocks if b["type"] == "image"}
    frame_hashes = {f: file_hash(within(job, figures[f]["path"])) for f in referenced}
    def action():
        # Clean auxiliary files only in this known, fixed build directory to avoid stale references.
        for suffix in (".aux", ".out", ".toc", ".log", ".pdf"):
            (build / ("lecture" + suffix)).unlink(missing_ok=True)
        copied = {}
        (build / "figures").mkdir(exist_ok=True)
        for fid in referenced:
            source = within(job, figures[fid]["path"])
            name = file_hash(source) + source.suffix.lower()
            shutil.copyfile(source, build / "figures" / name)
            copied[fid] = "figures/" + name
        def blocks(items):
            parts = []
            for b in items:
                if b["type"] == "text":
                    parts.append(escape(b["text"]) + "\n\n")
                elif b["type"] == "math":
                    parts.append("\\[\n" + b["latex"] + "\n\\]\n")
                else:
                    parts.append(r"\par\noindent\includegraphics[width=\linewidth,height=.29\textheight,keepaspectratio]{" + copied[b["frame_id"]] + "}\\par\n" + r"{\small " + escape(b.get("caption", "原画面证据")) + "}\\par\n")
            return "".join(parts)
        def unit(u, answer=False, continuation=False):
            ident = u["id"]
            title = ("解答：" if answer else TYPES[u["type"]] + "：") + u["title"]
            unbreakable = "[unbreakable]" if u["type"] == "exercise" or u.get("_fragment") else ""
            reserve = "\\Needspace{10\\baselineskip}\n" if not double else ""
            result = reserve + "\\begin{lessonbox}" + unbreakable + "{" + escape(title) + "}\n"
            if not answer and not continuation:
                result += "\\label{unit:" + ident + "}\n"
            label = ORIGIN[u["origin"]] + "；" + {"verified": "有核对记录", "pending": "待核对", "insufficient": "材料不足"}[u["review"]["status"]]
            result += "{\\small " + escape(label) + "}\\par\n"
            if not answer:
                if u["conditions"]:
                    result += r"\smalllabel{条件与适用范围}" + escape("；".join(u["conditions"])) + "\\par\n"
                result += blocks(u["body"])
            if u["type"] != "exercise" or answer:
                if u.get("motivation"):
                    result += r"\smalllabel{关键观察与方法动机}" + escape(u["motivation"]) + "\n"
                for i, s in enumerate(u.get("steps", []), 1 + u.get("_step_offset", 0)):
                    result += r"\smalllabel{" + f"步骤 {i}" + ("（" + ORIGIN[s["origin"]] + "）" if s["origin"] != u["origin"] else "") + "}\n" + blocks(s["content"])
                    result += "{\\small 依据：" + escape(s["basis"]) + "}\\par\n"
                if u["conclusion"]:
                    result += r"\smalllabel{结论}" + blocks(u["conclusion"])
                if u["pitfalls"]:
                    result += r"\smalllabel{易错点}" + escape("；".join(u["pitfalls"])) + "\n"
            if not answer:
                for ref in u["sources"]:
                    time_text = f"P{ref['part']} {stamp(ref['start'])} - {stamp(ref['end'])}"
                    link = source_link(manifest, ref["start"])
                    result += "\\par{\\small 来源：" + (r"\href{" + escape(link) + "}{" + escape(time_text) + "}" if link else escape(time_text)) + "}\\par\n"
                if u.get("external_url"):
                    from handout_core import public_url
                    result += r"\par{\small 外部来源：\url{" + escape(public_url(u["external_url"])) + "}}\n"
            if u["review"]["status"] != "verified":
                result += "\\par{\\small 待处理：" + escape(u["review"]["reason"]) + "}\\par\n"
            if u["type"] == "exercise" and not answer:
                result += "\\vspace{12mm}\n"
            return result + "\\end{lessonbox}\n"
        double = layout == "double"
        body = []
        if double:
            body.append("\\small\n\\begin{multicols}{2}\n")
        def add(u, answer=False):
            if double and u.get("wide"):
                body.append("\\end{multicols}\n" + unit(u, answer) + "\\clearpage\n\\begin{multicols}{2}\n")
            elif double and not answer and u["type"] == "example" and len(u.get("steps", [])) >= 2:
                # Split long derivations at a semantic step boundary, not inside a formula.
                cut = (len(u["steps"]) + 1) // 2
                first, second = copy.deepcopy(u), copy.deepcopy(u)
                first.update(steps=u["steps"][:cut], conclusion=[], pitfalls=[], sources=[], _fragment=True)
                second.update(title=u["title"] + "（续）", body=[], conditions=[], motivation="", steps=u["steps"][cut:], _fragment=True, _step_offset=cut)
                body.append(unit(first) + unit(second, continuation=True))
            else:
                body.append(unit(u, answer))
        for section in doc["sections"]:
            selected = [u for u in doc["units"] if u["section_id"] == section["id"] and u["type"] != "exercise" and u["origin"] not in ("comment", "external")]
            if selected:
                heading = "\\Needspace{14\\baselineskip}\n\\section*{" + escape(section["title"]) + "}\n"
                if double and selected[0].get("wide"):
                    body.append("\\end{multicols}\n" + heading + unit(selected[0]) + "\\clearpage\n\\begin{multicols}{2}\n")
                    for u in selected[1:]:
                        add(u)
                else:
                    if double:
                        body.append("\\end{multicols}\n" + heading + "\\begin{multicols}{2}\n")
                    else:
                        body.append(heading)
                    for u in selected:
                        add(u)
        extras = [u for u in doc["units"] if u["origin"] in ("comment", "external")]
        if extras:
            body.append(r"\section*{评论与外部补充（独立核对）}" + "\n")
            for u in extras:
                add(u)
        exercises = [u for u in doc["units"] if u["type"] == "exercise"]
        if exercises:
            if double:
                body.append("\\end{multicols}\n")
            body.append("\\clearpage\n\\section*{生成自测}\n")
            if double:
                body.append("\\begin{multicols}{2}\n")
            for u in exercises:
                add(u)
            if double:
                body.append("\\end{multicols}\n")
            body.append("\\clearpage\n\\section*{自测答案与解析}\n")
            if double:
                body.append("\\begin{multicols}{2}\n")
            for u in exercises:
                add(u, True)
        if double:
            body.append("\\end{multicols}\n")
        index = []
        for u in doc["units"]:
            times = [f"P{r['part']} {stamp(r['start'])} - {stamp(r['end'])}" for r in u["sources"]]
            suffix = "; ".join(times) or ORIGIN[u["origin"]] + "；关联 " + ", ".join(u.get("related_units", []))
            if u["sources"] and source_link(manifest, u["sources"][0]["start"]):
                suffix = r"\href{" + escape(source_link(manifest, u["sources"][0]["start"])) + "}{" + escape(suffix) + "}"
            else:
                suffix = escape(suffix)
            index.append(escape(u["title"]) + r" & \pageref{unit:" + u["id"] + "} & " + suffix + r"\\" + "\n")
        intro = ["课程阶段：" + escape(doc["level"]), "先修要求：" + escape("；".join(doc["prerequisites"]) or "无额外要求"),
                 "材料覆盖：" + escape(doc["coverage"]), f"来源：{escape(manifest['title'])}，P{manifest['part']}，{stamp(manifest['duration'])}"]
        if manifest.get("fixture"):
            intro.insert(0, r"\textbf{自制工程演示样本；不代表真实网课识别效果。}")
        if draft:
            intro.insert(0, r"\textbf{草稿：包含待核对内容，不能视为已验收讲义。}")
        font_tex = "\\setmainfont{texgyretermes-regular.otf}[BoldFont=texgyretermes-bold.otf,ItalicFont=texgyretermes-italic.otf,BoldItalicFont=texgyretermes-bolditalic.otf]\n\\setmathfont{texgyretermes-math.otf}\n"
        if fonts == "windows":
            font_tex += r"\setCJKmainfont{SimSun}[AutoFakeBold=2]"
        elif bundled_font.is_file():
            (build / "fonts").mkdir(exist_ok=True)
            shutil.copyfile(bundled_font, build / "fonts" / bundled_font.name)
            font_tex += r"\setCJKmainfont{SourceHanSerifSC-Regular.otf}[Path=fonts/,AutoFakeBold=2]"
        else:
            font_tex += r"\setCJKmainfont{Source Han Serif SC}[AutoFakeBold=2]"
        values = {"FONTS": font_tex, "TITLE": escape(doc["title"]), "LEVEL": escape(doc["level"]),
                  "STATUS": "草稿" if draft else "有内容核对记录", "LAYOUT": "单栏学习版" if layout == "single" else "双栏复习版",
                  "INTRO": "\\par\n".join(intro) + "\\par\n", "BODY": "".join(body), "INDEX": "".join(index),
                  "ISSUES": "\\section*{待核对清单}\n" + "\\par\n".join(escape(x["unit_id"] + "：" + x["reason"]) for x in report["issues"]) if report["issues"] else ""}
        tex = template.read_text(encoding="utf-8")
        tex = re.sub(r"@@([A-Z]+)@@", lambda m: values[m[1]], tex)
        (build / "lecture.tex").write_text(tex, encoding="utf-8")
        env = os.environ.copy()
        # Kpathsea file restrictions plus formula allowlist and isolated input tree.
        env.update(openin_any="p", openout_any="p", shell_escape="f")
        if engine == "tectonic":
            env.setdefault("TECTONIC_CACHE_DIR", str(job / "build/tex-cache"))
        args = ([executable, "--untrusted", "--keep-intermediates", "--keep-logs", "lecture.tex"] if engine == "tectonic" else
                [executable, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "lecture.tex"])
        logs = []
        for _ in range(1 if engine == "tectonic" else 3):
            try:
                p = subprocess.run(args, cwd=build, env=env, capture_output=True, timeout=300)
            except subprocess.TimeoutExpired as exc:
                partial = (exc.stdout or b"").decode("utf-8", errors="replace") + (exc.stderr or b"").decode("utf-8", errors="replace")
                (build / "compiler.log").write_text(partial, encoding="utf-8")
                raise HandoutError("排版超时；素材未丢失，可只重新排版") from exc
            logs.append(p.stdout.decode("utf-8", errors="replace") + p.stderr.decode("utf-8", errors="replace"))
            if p.returncode:
                (build / "compiler.log").write_text("\n".join(logs), encoding="utf-8")
                raise HandoutError("TeX 编译失败；查看 build/" + layout + "/compiler.log，检查编译器、字体和公式")
        log = "\n".join(logs) + (build / "lecture.log").read_text(encoding="utf-8", errors="replace") if (build / "lecture.log").exists() else "\n".join(logs)
        (build / "compiler.log").write_text(log, encoding="utf-8")
        warnings = [line for line in log.splitlines() if any(word in line for word in ("Overfull", "Missing character", "undefined references"))]
        write_json(build / "layout-report.json", {"engine": engine, "fonts": fonts, "warnings": sorted(set(warnings)),
                   "visual_review": "pending", "notice": "逐页检查缺字、溢出、分页和截图；编译成功不表示已通过视觉验收。"})
        aux = (build / "lecture.aux").read_text(encoding="utf-8")
        labels = dict(re.findall(r"\\newlabel\{unit:([^}]+)\}\{\{[^}]*\}\{(\d+)\}", aux))
        if any(u["id"] not in labels for u in doc["units"]):
            raise HandoutError("编译没有产生完整来源页码，未发布 PDF")
        dest = job / "deliverables"
        dest.mkdir(exist_ok=True)
        stem = "handout-" + layout + ("-draft" if draft else "")
        pdf = dest / (stem + ".pdf")
        index_csv = dest / (stem + "-source-index.csv")
        shutil.copyfile(build / "lecture.pdf", pdf)
        with index_csv.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["单元ID", "知识点/题目", "PDF页码", "分P", "起始", "结束", "链接", "来源类别"])
            for u in doc["units"]:
                for ref in u["sources"] or [{}]:
                    csv_title = "'" + u["title"] if u["title"].lstrip().startswith(("=", "+", "-", "@")) else u["title"]
                    writer.writerow([u["id"], csv_title, labels[u["id"]], ref.get("part", ""),
                                     stamp(ref["start"]) if ref else "", stamp(ref["end"]) if ref else "",
                                     source_link(manifest, ref["start"]) if ref else u.get("external_url", ""), ORIGIN[u["origin"]]])
        return [pdf, index_csv, build / "lecture.tex", build / "layout-report.json"]
    fingerprint = {"doc": doc, "source": manifest, "template": file_hash(template), "frames": frame_hashes,
                   "bundled_font": file_hash(bundled_font) if fonts == "sourcehan" and bundled_font.is_file() else None,
                   "layout": layout, "draft": draft, "engine": engine, "executable": executable, "fonts": fonts,
                   "code": file_hash(__file__)}
    return stage(job, "render_" + layout + ("_draft" if draft else ""), fingerprint, action)
