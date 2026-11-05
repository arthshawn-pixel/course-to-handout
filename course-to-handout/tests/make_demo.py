"""Create an explicitly synthetic 10-minute lesson and evidence-aligned handout.

Usage: python tests/make_demo.py OUTPUT_DIRECTORY
Requires Pillow and optional media dependencies. Does not contact any course site.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from handout_core import read_json, write_json
from handout_media import ffmpeg_path


def text(s): return {"type": "text", "text": s}
def formula(s): return {"type": "math", "latex": s}


TRANSCRIPT = [
    (0, 35, "本节是自编工程演示：用导数研究单调性、极值和最值。定义域与条件必须先写清楚。"),
    (35, 75, "函数在一个区间上可导，如果导数处处大于零，那么函数严格递增。导数等于零不一定有极值，比如 x 的三次方在零点。"),
    (75, 120, "闭区间最值要比较所有内部驻点和两个端点的函数值。驻点只是候选，不是最终答案。"),
    (120, 165, "例一：函数 f(x)=x^3-3x，定义域限制在闭区间 [-2,2]，求单调区间、极值与最值。"),
    (165, 210, "求导得到 f'(x)=3x^2-3=3(x-1)(x+1)，驻点为负一和一。"),
    (210, 255, "导数在负二到负一为正，负一到一为负，一到二为正。于是先增、再减、再增。"),
    (255, 300, "负一处极大值为二，一处极小值为负二。注意极值是局部概念。"),
    (300, 360, "比较端点与驻点：f(-2)=-2，f(-1)=2，f(1)=-2，f(2)=2。最大值二在负一和二取得，最小值负二在负二和一取得。"),
    (360, 410, "例二：证明对每个正数 x，ln x 不大于 x-1，并指出等号成立的条件。"),
    (410, 460, "作差构造 g(x)=x-1-ln x，定义域为正数。求导得到 g'(x)=1-1/x=(x-1)/x。"),
    (460, 510, "因为分母为正，g 在零到一递减，在一到正无穷递增。"),
    (510, 560, "g 在一处取得全局最小值零，因此不等式成立，且仅当 x=1 时取等号。"),
    (560, 600, "方法总结：证明全称不等式可转为求差函数的全局最小值；注意对数的定义域以及等号条件。")
]


def make_content(source, frame_ids):
    vid = source["video_id"]
    def ref(a, b, subs, fids):
        return [{"video_id": vid, "part": source["part"], "start": a, "end": b,
                 "subtitle_ids": [f"s{i:05d}" for i in subs], "frame_ids": fids}]
    def step(content, basis, origin="course"):
        return {"content": content, "basis": basis, "origin": origin}
    def unit(ident, section, kind, title, a, b, subs, frames):
        return {"id": ident, "section_id": section, "type": kind, "origin": "course", "title": title,
                "original_text": "\n".join(TRANSCRIPT[i - 1][2] for i in subs), "raw_recognition": [],
                "conditions": [], "body": [], "motivation": "", "steps": [], "conclusion": [], "pitfalls": [],
                "related_units": [], "sources": ref(a, b, subs, frames),
                "review": {"status": "pending", "reason": "自编工程样本，需按素材逐项核对；不能代表真实课程效果"}}
    u1 = unit("u1", "c1", "theorem", "从导数到单调性与最值", 0, 120, [1, 2, 3], [frame_ids[60]])
    u1.update(wide=True, conditions=["函数在所讨论开区间内可导；闭区间最值问题要求闭区间上连续"],
              body=[text("若在一个区间内处处有正导数，则函数在该区间严格递增。闭区间最值需要同时检查内部驻点和端点。")],
              conclusion=[formula(r"f'(x)>0\ \Longrightarrow\ f\text{ 在区间内严格递增}"),
                          text("f′(x₀)=0 不是存在极值的充分条件。")],
              pitfalls=["不要把充分条件误写为必要条件；零导数点不一定是极值点", "本节例题均在内部可导；一般最值问题还应检查不可导点"])
    u2 = unit("u2", "c2", "example", "三次函数的极值与闭区间最值", 120, 360, list(range(4, 9)), [frame_ids[150], frame_ids[240], frame_ids[330]])
    u2.update(wide=True, conditions=["x 属于闭区间 [-2,2]；函数为多项式，连续且可导"],
              body=[text("求下列函数的单调区间、极值与最大值、最小值，并写出取得最值的位置。"),
                    formula(r"f(x)=x^3-3x,\qquad x\in[-2,2]"),
                    {"type": "image", "frame_id": frame_ids[150], "caption": "自编原画面：例一完整题干，P1 00:02:30"}],
              motivation="极值由导数变号判断；闭区间最值再比较端点和内部驻点，避免遗漏端点或重复取得最值的位置。",
              steps=[step([formula(r"f'(x)=3x^2-3=3(x-1)(x+1)=0\iff x=\pm1")], "求导法则与因式分解"),
                     step([text("在 (-2,-1) 和 (1,2) 内导数为正，在 (-1,1) 内导数为负；因此函数先增、再减、再增。")], "导数符号与单调性的充分条件"),
                     step([formula(r"f(-1)=2,\qquad f(1)=-2")], "-1 处导数由正变负，1 处由负变正"),
                     step([formula(r"f(-2)=-2,\quad f(-1)=2,\quad f(1)=-2,\quad f(2)=2")], "闭区间连续函数的最值只能在端点或内部驻点取得（本题处处可导）")],
              conclusion=[text("极大值为 2，在 x=-1 取得；极小值为 -2，在 x=1 取得。最大值为 2，在 x=-1 或 x=2 取得；最小值为 -2，在 x=-2 或 x=1 取得。")],
              pitfalls=["端点不能漏检；取得最大值的位置可能不止一个", "局部极值和区间最值的概念不同"])
    u3 = unit("u3", "c3", "example", "用导数证明对数不等式", 360, 600, list(range(9, 14)), [frame_ids[390], frame_ids[540]])
    u3.update(conditions=["x>0，保证自然对数有定义"],
              body=[text("证明以下不等式，并写出等号成立的充要条件。"), formula(r"\ln x\le x-1\qquad(x>0)")],
              motivation="将不等式转为差函数非负，再用单调性寻找它的全局最小值。",
              steps=[step([formula(r"g(x)=x-1-\ln x,\qquad g'(x)=1-\frac1x=\frac{x-1}{x}")], "作差及对数求导"),
                     step([text("分母 x>0，因此 g′ 的符号由 x-1 决定：g 在 (0,1) 严格递减，在 (1,+∞) 严格递增。")], "定义域内的导数符号"),
                     step([formula(r"g(x)\ge g(1)=1-1-\ln1=0")], "两侧严格单调，x=1 是唯一全局最小值点")],
              conclusion=[formula(r"\ln x\le x-1,\quad \text{等号成立}\iff x=1")],
              pitfalls=["不能把定义域扩成所有实数", "证明非负后还要核对等号是否唯一"])
    exercises = []
    specs = [
        ("e1", "概念理解：驻点一定是极值点吗", "u1", [text("判断命题：若 f′(x₀)=0，则 x₀ 一定是极值点。若错误，请给出反例。")],
         "寻找导数为零但函数仍在两侧同向变化的例子。", [formula(r"f(x)=x^3,\quad f'(0)=0"), text("x³ 在整个实数轴严格递增，因此 0 不是极值点。")], "命题错误；驻点不是极值的充分条件。", "反例法；严格单调函数在内部没有局部极值"),
        ("e2", "条件辨析：开区间上的最值", "u2", [text("若将例一的定义域改为 (-1,1)，函数是否取得最大值和最小值？")],
         "开区间没有包含两端点，需区分最值与上、下确界。", [text("f 在 (-1,1) 上严格递减，左右端极限分别为 2 和 -2，且区间内均取不到。")], "无最大值、无最小值；上确界为 2，下确界为 -2。", "严格单调性与端点不包含"),
        ("e3", "方法迁移：带参数的对数最小值", "u3", [text("设 a>0，求 h(x)=a·x-ln x（x>0）的最小值及取得位置。")],
         "参数为正，导数的唯一零点仍在定义域内；比较它两侧的符号。", [formula(r"h'(x)=a-\frac1x,\quad h'(x)=0\iff x=\frac1a"), text("在 (0,1/a) 递减，在 (1/a,+∞) 递增。"), formula(r"h\left(\frac1a\right)=1-\ln\frac1a=1+\ln a")], "唯一最小值为 1+ln a，在 x=1/a 取得。", "导数变号与对数运算")
    ]
    for ident, title, related, body, motivation, solution, answer, basis in specs:
        u = unit(ident, "c3", "exercise", title, 0, 1, [], [])
        u.update(origin="generated", original_text="", related_units=[related], sources=[], conditions=["自编生成题，非真实考试题"],
                 body=body, motivation=motivation, steps=[step(solution, basis, "generated")], conclusion=[text(answer)], pitfalls=[])
        exercises.append(u)
    return {"schema_version": 1, "title": "导数、极值与最值：自学讲义", "level": "高中数学",
            "prerequisites": ["多项式与自然对数的求导", "单调性、极值和闭区间最值的概念"],
            "coverage": "自编 10 分钟合成视频 + 完整自编字幕 + 指定时间板书；工程演示，所有内容保留待核对状态。没有真实网课、ASR 或 OCR 准确率结论。",
            "sections": [{"id": "c1", "title": "一、先确认适用条件", "start": 0, "end": 120, "origin": "human"},
                         {"id": "c2", "title": "二、区分极值与最值", "start": 120, "end": 360, "origin": "human"},
                         {"id": "c3", "title": "三、从不等式转为最值", "start": 360, "end": 600, "origin": "human"}],
            "units": [u1, u2, u3, *exercises]}


def main():
    p = argparse.ArgumentParser(); p.add_argument("output"); args = p.parse_args()
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw, ImageFont
    fontfile = Path("C:/Windows/Fonts/simsun.ttc")
    if not fontfile.exists():
        raise RuntimeError("演示生成器使用 Windows 宋体；其他环境请替换为可用中文字体文件")
    font = ImageFont.truetype(str(fontfile), 44)
    heading = ImageFont.truetype(str(fontfile), 58)
    boards = [
        ["导数与最值：先写条件", "函数在区间内可导", "f'(x)>0  => 严格递增（充分条件）", "f'(x0)=0 不一定有极值：f(x)=x^3", "闭区间最值：比较端点与内部驻点"],
        ["例一：完整题干", "f(x)=x^3-3x，x 属于 [-2,2]", "求单调区间、极值和最值。", "请写出所有取得最值的位置。"],
        ["例一：关键推导", "f'(x)=3(x-1)(x+1)", "(-2,-1)：+；(-1,1)：-；(1,2)：+", "f(-1)=2（极大）；f(1)=-2（极小）", "f(-2)=-2；f(2)=2", "最大值 2：x=-1,2；最小值 -2：x=-2,1"],
        ["例二：证明对数不等式", "ln x <= x-1，x>0", "指出等号成立条件。", "作差：g(x)=x-1-ln x", "g'(x)=(x-1)/x"],
        ["例二：全局最小值", "x>0，导数符号由 x-1 决定", "(0,1)：递减；(1,+∞)：递增", "g(x)>=g(1)=0", "所以 ln x <= x-1", "等号成立当且仅当 x=1"]
    ]
    for i, lines in enumerate(boards):
        image = Image.new("RGB", (1600, 900), "#f8f7f2"); d = ImageDraw.Draw(image)
        d.rectangle((50, 45, 65, 780), fill="#284b63")
        for j, line in enumerate(lines):
            d.text((100, 80 + j * 100), line, fill="#172f42", font=heading if j == 0 else font)
        d.text((100, 800), "自制工程样本 / 无真人课程内容 / 静音轨道", fill="#536570", font=font)
        image.save(output / f"board-{i}.png")
    durations = [120, 90, 150, 140, 100]
    concat = "".join(f"file 'board-{i}.png'\nduration {d}\n" for i, d in enumerate(durations)) + "file 'board-4.png'\n"
    (output / "boards.txt").write_text(concat, encoding="ascii")
    if not (output / "lesson.mp4").is_file():
        result = subprocess.run([ffmpeg_path(), "-nostdin", "-hide_banner", "-y", "-f", "concat", "-safe", "1", "-i", "boards.txt",
                             "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "600", "-vf", "fps=1",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "32k", "lesson.mp4"],
                            cwd=output, capture_output=True, timeout=120)
        if result.returncode: raise RuntimeError(result.stderr.decode(errors="replace"))
    def ts(sec): return f"{sec // 3600:02}:{sec // 60 % 60:02}:{sec % 60:02},000"
    (output / "lesson.srt").write_text("\n\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{s}" for i, (a,b,s) in enumerate(TRANSCRIPT, 1)), encoding="utf-8")
    cli = Path(__file__).resolve().parents[1] / "scripts/lecture.py"
    job = output / "job"
    commands = [["init", str(job), "--video", str(output / "lesson.mp4"), "--title", "自编演示：导数与最值", "--level", "高中", "--fixture"],
                ["subtitles", str(job), str(output / "lesson.srt")],
                ["frames", str(job), "--times", "60", "150", "240", "330", "390", "540"],
                ["audio", str(job)], ["prepare", str(job), "--chunk", "120"]]
    if (job / "state.json").is_file():
        commands = commands[1:]
    for command in commands:
        subprocess.run([sys.executable, str(cli), *command], check=True)
    frames = {int(f["time"]): f["id"] for f in read_json(job / "materials/frames.json")}
    write_json(job / "handout.json", make_content(read_json(job / "source.json"), frames))
    subprocess.run([sys.executable, str(cli), "check", str(job)], check=True)
    print(json.dumps({"job": str(job), "fixture": True}, ensure_ascii=False))


if __name__ == "__main__": main()
