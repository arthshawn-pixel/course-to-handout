"""Public subtitle access probe and credential-free browser export contract."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlencode

from handout_core import HandoutError, read_json, write_json, number


def subtitle_status(player_payload):
    if not isinstance(player_payload, dict) or player_payload.get('code') != 0:
        return {'status': 'read_failed', 'reason': '字幕元数据接口未成功返回；未推断为未登录'}
    data = player_payload.get('data', {})
    tracks = data.get('subtitle', {}).get('subtitles', [])
    languages = [t['lan'] for t in tracks if isinstance(t, dict) and t.get('lan') and t.get('subtitle_url')]
    if languages:
        return {'status': 'available', 'languages': languages, 'reason': '当前会话返回字幕轨；还需取得正文并导入'}
    if data.get('need_login_subtitle') is True:
        return {'status': 'waiting_login', 'languages': [], 'reason': 'B站接口明确要求字幕读取会话登录；不影响已取得的视频'}
    return {'status': 'not_returned', 'languages': [], 'reason': '当前会话未返回字幕；不能据此证明视频无字幕'}


def public_subtitle_probe(job):
    """Never reads a browser profile or credentials; login must happen in the host."""
    job = Path(job).resolve()
    source = read_json(job / 'source.json')
    url = urlsplit(source.get('url', ''))
    match = re.fullmatch(r'/video/(BV[0-9A-Za-z]+|av\d+)/?', url.path)
    if url.scheme != 'https' or url.hostname not in ('bilibili.com', 'www.bilibili.com') or not match:
        raise HandoutError('字幕状态探测仅支持任务中的 B 站视频链接')
    def get(endpoint, query):
        request = urllib.request.Request('https://api.bilibili.com/' + endpoint + '?' + urlencode(query),
                    headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    try:
        identity = {'bvid': match[1]} if match[1].startswith('BV') else {'aid': match[1][2:]}
        metadata = get('x/web-interface/view', identity)
        if metadata.get('code') != 0:
            raise HandoutError('无法确认视频身份；未推断为需要登录')
        data = metadata.get('data', {})
        page = next((p for p in data.get('pages', []) if p.get('page') == source['part']), None)
        if not page:
            raise HandoutError('返回素材中没有任务指定的分 P')
        payload = get('x/player/wbi/v2', {'aid': data['aid'], 'cid': page['cid']})
        result = subtitle_status(payload)
        result.update(scope='subtitles', method='unauthenticated_public_probe', bvid=data.get('bvid'), part=source['part'], cid=page['cid'])
    except urllib.error.HTTPError as exc:
        result = {'status': 'read_failed', 'scope': 'subtitles', 'code': 'http_' + str(exc.code), 'reason': '字幕元数据请求失败；未推断为需要登录'}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result = {'status': 'read_failed', 'scope': 'subtitles', 'code': type(exc).__name__, 'reason': '网络请求失败；保留已有视频和材料'}
    record_subtitle_probe(job, result)
    return result


def record_subtitle_probe(job, result):
    job = Path(job)
    state = read_json(job / 'state.json')
    state.setdefault('subtitle_checks', {})['unauthenticated_public_probe'] = result
    local = read_json(job / 'materials/subtitles.json')
    # An unauthenticated check cannot invalidate a transcript already exported
    # successfully by the authenticated browser and stored locally.
    if not local:
        state.setdefault('resource_access', {})['subtitles'] = result
    write_json(job / 'state.json', state)
    write_json(job / 'materials/subtitle-access.json', result)


def validate_browser_export(payload, source):
    def exact_keys(value, allowed, label):
        if not isinstance(value, dict) or set(value) - set(allowed):
            raise HandoutError(f'{label} 包含未知字段；使用随包导出程序，避免保存会话或无关网页数据')
    exact_keys(payload, ['status','schema_version','source','track','body','captured_at'], '字幕导出')
    if payload.get('status') != 'exported' or payload.get('schema_version') != 1:
        raise HandoutError('浏览器没有成功导出完整字幕；登录或读取状态不能当作字幕导入')
    if not isinstance(payload.get('captured_at'), str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', payload['captured_at']):
        raise HandoutError('字幕导出时间必须为 UTC ISO 时间文本')
    identity, track = payload.get('source'), payload.get('track')
    exact_keys(identity, ['bvid','aid','part','cid','duration','title'], '字幕来源')
    exact_keys(track, ['language','label','is_ai'], '字幕轨')
    source_id = re.sub(r'_p\d+$', '', source['video_id'])
    same_video = identity.get('bvid') == source_id
    if source_id.startswith('av') and source_id[2:].isdigit():
        same_video = type(identity.get('aid')) is int and identity['aid'] == int(source_id[2:]) and isinstance(identity.get('bvid'),str) and bool(re.fullmatch(r'BV[0-9A-Za-z]+',identity['bvid']))
    if not same_video or type(identity.get('part')) is not int or identity['part'] != source['part']:
        raise HandoutError('字幕导出的视频或分 P 与任务不符')
    if type(identity.get('cid')) is not int or identity['cid'] <= 0:
        raise HandoutError('字幕导出缺少有效 CID')
    if not number(identity.get('duration')) or abs(identity['duration'] - source['duration']) > 1:
        raise HandoutError('字幕导出的时长与任务视频不符')
    if not isinstance(track.get('language'), str) or not track['language'] or type(track.get('is_ai')) is not bool:
        raise HandoutError('字幕轨缺少语言或 AI 来源标记')
    body = payload.get('body')
    if not isinstance(body, list) or not body:
        raise HandoutError('导出字幕为空')
    for segment in body:
        exact_keys(segment, ['from','to','content'], '字幕片段')
        a, b, text = segment.get('from'), segment.get('to'), segment.get('content')
        if not number(a) or not number(b) or not 0 <= a < b <= source['duration'] + .05 or not isinstance(text,str) or not text.strip():
            raise HandoutError('导出字幕时间越界或正文无效')
    return payload
