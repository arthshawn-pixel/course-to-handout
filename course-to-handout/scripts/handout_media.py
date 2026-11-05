"""Local media and bounded Bilibili acquisition. No browser credential scraping."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from handout_core import HandoutError, public_url, read_json, write_json, file_hash, stage, within, number

BILIBILI_FORMAT = "bestvideo[height<=1080][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"


def ffmpeg_path():
    if os.environ.get("HANDOUT_FFMPEG"):
        return os.environ["HANDOUT_FFMPEG"]
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    if importlib.util.find_spec("imageio_ffmpeg"):
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    raise HandoutError("缺少 FFmpeg。安装 FFmpeg 或 pip install imageio-ffmpeg；也可设置 HANDOUT_FFMPEG")


def run_media(args, timeout=300):
    from handout_workflow import run_tool
    try:
        p = run_tool([ffmpeg_path(), "-nostdin", "-hide_banner", *args], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise HandoutError("FFmpeg 超时，任务已保留，可重试当前步骤") from exc
    if p.returncode:
        raise HandoutError("FFmpeg 处理失败；检查媒体是否损坏、时间点和编码是否可读")
    return p


def media_info(path):
    from handout_workflow import run_tool
    p = run_tool([ffmpeg_path(), "-nostdin", "-hide_banner", "-i", str(Path(path).resolve())], capture_output=True, timeout=30)
    log = p.stderr.decode("utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", log)
    if not m:
        raise HandoutError("无法探测视频时长，请提供可读的本地视频")
    return {"duration": int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), "audio": "Audio:" in log,
            "video": "Video:" in log}


def extract_frames(job, times, interval_seconds=60):
    job = Path(job).resolve()
    manifest = read_json(job / "source.json")
    media = within(job, manifest["media_path"]) if manifest.get("media_path") else None
    if not media or not media.exists():
        raise HandoutError("缺少本地视频；可用 add-frame 导入带时间戳截图")
    duration = manifest["duration"]
    if times is None:
        if not number(interval_seconds) or interval_seconds < 1:
            raise HandoutError("扫描间隔至少为 1 秒")
        times = list(range(0, max(1, int(duration)), int(interval_seconds)))
    if len(times) > 500:
        raise HandoutError("一次最多抽取 500 帧；请缩小时间范围")
    if not all(number(t) and 0 <= t < duration for t in times):
        raise HandoutError("截图时间必须位于视频时长内")
    results = []
    for t in sorted(set(round(t, 3) for t in times)):
        ident = f"f{round(t * 1000):09d}"
        output = job / "materials" / "frames" / (ident + ".png")
        output.parent.mkdir(parents=True, exist_ok=True)
        def action():
            # Input seek + accurate_seek decodes/discards from the preceding keyframe,
            # preserving time accuracy without decoding the whole prefix for every image.
            run_media(["-y", "-ss", str(t), "-accurate_seek", "-i", str(media), "-frames:v", "1", "-vf", "scale=1600:-2", str(output)])
            if not output.is_file() or output.stat().st_size == 0:
                raise HandoutError("该时间点没有可解码画面")
            return [output]
        results.append(stage(job, "frame_" + ident, {"media": file_hash(media), "time": t, "seek": "accurate-input"}, action))
        frames = read_json(job / "materials" / "frames.json")
        frames = [f for f in frames if f["id"] != ident]
        frames.append({"id": ident, "time": t, "path": str(output.relative_to(job).as_posix()), "origin": "ffmpeg",
                       'video_id':manifest['video_id'],'part':manifest['part']})
        write_json(job / "materials" / "frames.json", sorted(frames, key=lambda x: x["time"]))
    return results


def extract_audio(job):
    job = Path(job).resolve()
    source = read_json(job / "source.json")
    if not source.get("media_path"):
        raise HandoutError("没有本地视频")
    media = within(job, source["media_path"])
    if not media_info(media)["audio"]:
        raise HandoutError("视频没有音轨；请补传字幕，不按标题推测正文")
    output = job / "materials" / "audio.wav"
    def action():
        run_media(["-y", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000", str(output)], timeout=1800)
        return [output]
    return stage(job, "audio", {"media": file_hash(media)}, action)


def acquire_bilibili(job):
    """Public/authorized extractor access only. Browser is a separate skill capability."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise HandoutError("缺少 yt-dlp；安装 requirements-media.txt 后再获取") from exc
    job = Path(job).resolve()
    manifest = read_json(job / "source.json")
    url = public_url(manifest.get("url", ""))
    parts = urlsplit(url)
    if parts.hostname not in ("www.bilibili.com", "bilibili.com") or not re.fullmatch(r"/video/(?:BV[0-9A-Za-z]+|av\d+)/?", parts.path):
        raise HandoutError("首版获取仅支持 bilibili.com/video/BV… 或 av… 链接；网盘请先下载本地文件")
    requested_part = manifest["part"]
    url = urlsplit(url)._replace(query=f"p={requested_part}").geturl()
    class Quiet:
        login_required = False
        def debug(self, msg): pass
        def warning(self, msg):
            if 'Subtitles are only available when logged in' in msg:
                self.login_required = True
        def error(self, msg): pass
    logger = Quiet()
    directory = job / "materials" / "download"
    directory.mkdir(parents=True, exist_ok=True)
    options = {"outtmpl": str(directory / "source.%(ext)s"), "noplaylist": True,
               "playlist_items": str(requested_part),
               "format": BILIBILI_FORMAT,
               "merge_output_format": "mp4",
               "writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": ["zh.*", "ai-zh.*"],
               "retries": 1, "fragment_retries": 1, "extractor_retries": 1,
               "socket_timeout": 20, "logger": logger, "quiet": True,
               "ffmpeg_location": ffmpeg_path(), "overwrites": False,
               "writethumbnail": False, "writeinfojson": False}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        message = str(exc)
        http_code = re.search(r"HTTP Error (\d{3})", message)
        category = ("format_unavailable" if "Requested format is not available" in message else
                    "login_required" if re.search(r"(?:log[ -]?in|login required)", message, re.I) else
                    "http_" + http_code[1] if http_code else "network_or_extractor")
        state = read_json(job / "state.json")
        state["access"] = {"status": "waiting_materials", "category": category,
                           "reason": "独立获取失败；根据错误类别检查格式、网络或登录；不把未知错误自动归为未登录。"}
        write_json(job / "state.json", state)
        raise HandoutError(f"B 站获取失败（{category}）；按错误类别核实，或补传文件。未保存凭证和原始错误。") from exc
    if not info or info.get("_type") in ("playlist", "multi_video"):
        raise HandoutError("返回多视频结果，无法确认分 P；请导入指定分 P 文件")
    actual_part = re.search(r"_p(\d+)$", str(info.get("id", "")))
    if (actual_part and int(actual_part[1]) != requested_part) or (requested_part > 1 and not actual_part):
        raise HandoutError("下载结果无法确认所选分 P，未作为任务素材使用；请导入指定分 P 文件")
    media_files = [p for p in directory.iterdir() if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".flv")]
    if len(media_files) != 1:
        raise HandoutError("没有得到唯一可读视频，请补传指定分 P 文件")
    media = media_files[0]
    detected = media_info(media)
    manifest.update(media_path=str(media.relative_to(job).as_posix()), duration=detected["duration"],
                    title=info.get("title", manifest["title"]), video_id=info.get("bvid") or info.get("id") or manifest["video_id"],
                    acquisition="yt-dlp; session independent")
    write_json(job / "source.json", manifest)
    state = read_json(job / "state.json")
    state["access"] = {"status": "ready", "reason": "独立获取已得到视频；字幕须另行导入并校验"}
    subtitle_candidates = [p.name for p in directory.iterdir() if p.suffix in ('.srt','.vtt','.json')]
    state.setdefault('resource_access', {})['subtitles'] = {
        'status': 'available' if subtitle_candidates else 'waiting_login' if logger.login_required else 'not_returned',
        'method': 'yt_dlp', 'reason': '字幕须在可读会话中取得并导入；视频成功不代表字幕已取得'}
    write_json(job / "state.json", state)
    return {"media": manifest["media_path"], "subtitle_candidates": subtitle_candidates}
