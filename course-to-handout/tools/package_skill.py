"""Build WorkBuddy upload ZIP from canonical skill, excluding test/runtime data."""
import argparse
import json
import re
import zipfile
from pathlib import Path


def package(root, output):
    root = Path(root).resolve()
    source = (root / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)", source, re.S)
    if not match: raise ValueError("Invalid SKILL.md")
    metadata = '\ndisplay_name: "网课转讲义"\ndisplay_name_en: "Course to Handout"\ndescription_zh: "支持B站、本地及百度浏览器下载交接的理工与经管课程讲义"\ndescription_en: "Create traceable STEM and business handouts from course videos"\nversion: "0.4.0"\nauthor: "Course to Handout Project"\nexamples_zh:\n  - "把这段课程整理成含完整解答的单栏讲义"\n'
    workbuddy_md = "---\n" + match[1] + metadata + "---\n" + match[2]
    output = Path(output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("course-to-handout/SKILL.md", workbuddy_md)
        for folder in ("scripts", "references", "templates", "assets"):
            for path in sorted((root / folder).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    archive.write(path, "course-to-handout/" + path.relative_to(root).as_posix()); count += 1
        archive.write(root / "requirements-media.txt", "course-to-handout/requirements-media.txt")
    return {"zip": str(output), "support_files": count, "platform": "WorkBuddy", "version": "0.4.0"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("output"); args = p.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parents[1], args.output), ensure_ascii=False))
