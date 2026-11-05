"""Browser-led Baidu acquisition. User login stays in the official UI.

This module never controls a browser, reads account cookies or calls private
download APIs. The host agent operates its supported browser; these commands
persist observed state and validate the resulting local video.
"""
from __future__ import annotations

import os
import re
import shutil
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs,urlsplit

from handout_core import HandoutError,read_json,write_json,file_hash,digest,within

VIDEO_EXTENSIONS={'.mp4','.mkv','.mov','.avi','.webm','.m4v','.flv','.ts','.wmv'}
PARTIAL_SUFFIXES=('.crdownload','.part','.partial','.download','.downloading','.tmp','.aria2','.baiduyun.p.downloading')
TASK='acquisition/baidu.json'
PRIVATE='acquisition/private-baidu-request.json'
NEXT={
 'awaiting_browser':'用宿主支持的浏览器打开plan中的官方分享URL，实际观察页面。',
 'waiting_login':'请用户在该官方页面/客户端自行登录；回复完成后重新观察，不轮询。',
 'waiting_extraction_code':'请用户提供分享提取码或在官方页面自行输入；不是账号密码。',
 'waiting_verification':'请用户自行完成验证码/验证，再重新观察页面。',
 'waiting_selection':'只选择用户需要的一个视频，调用baidu-select；文件夹先由浏览器展开。',
 'ready_to_download':'用官方页面或已安装客户端只下载所选视频，保存到plan给出的目录。',
 'downloading':'等待所选视频下载，调用baidu-watch；不得把下载任务建立当作文件取得。',
 'checking_download':'等待文件稳定，再调用baidu-watch。',
 'validation_failed':'查看diagnostics/baidu_import.json，修复所选视频或下载状态；不要把校验失败当成功。',
 'tool_unavailable':'保留任务；恢复可验证URL的浏览器工具后继续，不私接调试接口。',
 'paused':'用户已暂停，收到明确继续请求后记录resumed。',
 'acquired':'视频校验完成。',
}

def parse_share(text,code=None):
    if not isinstance(text,str) or len(text)>10000:raise HandoutError('BAIDU_LINK: 提供一个分享链接或完整分享文本')
    found=[]
    for raw in re.findall(r'https?://[^\s<>"“”]+',text.replace('\u00a0',' ')):
        try:
            p=urlsplit(raw.rstrip('，。,;；)）'))
            if p.scheme!='https' or p.hostname!='pan.baidu.com' or p.username or p.password or p.port not in (None,443):continue
        except ValueError:continue
        q=parse_qs(p.query);m=re.fullmatch(r'/s/(1[A-Za-z0-9_-]{5,80})/?',p.path)
        ident=m[1] if m else '1'+q['surl'][0] if p.path=='/share/init' and len(q.get('surl',[]))==1 else None
        if ident and re.fullmatch(r'1[A-Za-z0-9_-]{5,80}',ident):found.append((ident,q.get('pwd',[])))
    if not found or len({f[0] for f in found})!=1:raise HandoutError('BAIDU_LINK: 需要一个有效的百度分享；多个分享分别建任务')
    codes=([str(code)] if code else [])+[v for _,values in found for v in values]
    codes+=re.findall(r'(?:提取码|提取碼|访问码|访问碼)\s*[:：]?\s*([A-Za-z0-9]{4})(?![A-Za-z0-9])',text)
    if any(not re.fullmatch(r'[A-Za-z0-9]{4}',c) for c in codes):raise HandoutError('BAIDU_CODE: 提取码须为4位字母数字')
    if len(set(codes))>1:raise HandoutError('BAIDU_CODE_CONFLICT: 链接与文本的提取码不一致')
    return {'url':'https://pan.baidu.com/s/'+found[0][0],'share_id':found[0][0],'code':codes[0] if codes else None}

def _task(job):return read_json(Path(job)/TASK)

def _save(job,task,status=None):
    job=Path(job)
    if status:task['status']=status
    task['updated_at']=time.time();task['next_action']=NEXT[task['status']]
    if task['status']=='acquired' and task['intent']=='video_only':task['next_action']='用户只要求提取视频：到此停止，不生成讲义或PDF。'
    elif task['status']=='acquired':task['next_action']='素材就绪；继续字幕、抽帧与讲义流程。'
    write_json(job/TASK,task)
    state=read_json(job/'state.json')
    state.setdefault('resource_access',{})['media']={'provider':'baidu','status':task['status'],'next_action':task['next_action']}
    access='ready' if task['status']=='acquired' else 'paused' if task['status']=='paused' else task['status'] if task['status'] in ('waiting_login','waiting_verification') else 'waiting_materials'
    state['access']={'status':access,'reason':task['next_action']};write_json(job/'state.json',state)
    return status_report(job,task)

def initialize(job,text,code=None,title='百度网盘视频',level='待确认',intent='handout'):
    from lecture import initialize as init
    if intent not in ('handout','video_only'):raise HandoutError('BAIDU_INTENT: handout 或 video_only')
    share=parse_share(text,code)
    init(SimpleNamespace(job=job,video=None,url=share['url'],duration=None,title=title,level=level,part=1,video_id='baidu-'+share['share_id'],fixture=False))
    job=Path(job).resolve();source=read_json(job/'source.json');source.update(provider='baidu',source_kind='browser_share_video')
    write_json(job/'source.json',source);write_json(job/PRIVATE,share)
    task={'schema_version':1,'provider':'baidu','status':'awaiting_browser','share_url':share['url'],'share_id':share['share_id'],
          'intent':intent,'files':[],'selected':None,'observations':[],'download_started':False,'created_at':time.time()}
    _save(job,task);return plan(job)

def status_report(job,task=None):
    job=Path(job).resolve();task=task or _task(job)
    result={k:task.get(k) for k in ('provider','status','share_url','intent','files','selected','next_action','download_started','download_completed','download_progress')}
    result['job']=str(job)
    if task.get('download_dir'):result['download_directory']=str(within(job,task['download_dir']))
    if task['status']=='acquired':
        receipt=task.get('receipt',{});p=within(job,receipt.get('media_path','missing'))
        source=read_json(job/'source.json');artifact=job/'acquisition/baidu-receipt.json'
        valid=(p.is_file() and file_hash(p)==receipt.get('sha256') and receipt.get('checker_sha256')==file_hash(__file__)
               and source.get('media_path')==receipt.get('media_path') and source.get('media_sha256')==receipt.get('sha256')
               and artifact.is_file() and read_json(artifact)==receipt)
        result.update(receipt=receipt,media_current=valid)
        if not valid:result.update(status='validation_stale',next_action='实际视频已缺失或变更，先恢复/重新导入，不能沿用旧完成状态。')
    return result

def plan(job):
    job=Path(job).resolve();task=_task(job);result=status_report(job,task);private=read_json(job/PRIVATE)
    result['browser']={'official_url':private['url'],'extraction_code':private['code'],
                       'login':'user_only','credentials':'do_not_read_or_export','selection':'one_video_per_job'}
    result['required_host_capabilities']=['observe_current_url','read_share_file_list','official_download_action','known_download_destination_or_result_path']
    return result

def set_code(job,code):
    private=read_json(Path(job)/PRIVATE);updated=parse_share(private['url'],code)
    task=_task(job)
    if task['status'] in ('acquired','paused') or task.get('download_started'):raise HandoutError('BAIDU_CODE_STATE: 当前阶段不更改提取码')
    write_json(Path(job)/PRIVATE,updated);return _save(job,task,'awaiting_browser')

def _observed_url(url,share_id,allow_login=False):
    if not isinstance(url,str) or len(url)>4096:raise HandoutError('BAIDU_OBSERVATION_URL: 需要工具实际观察的网址')
    try:
        p=urlsplit(url)
        if p.port not in (None,443):raise ValueError('port')
    except ValueError:raise HandoutError('BAIDU_OBSERVATION_URL: 网址无效') from None
    if p.scheme!='https' or p.username or p.password:raise HandoutError('BAIDU_PAGE_MISMATCH: 不是预期的官方HTTPS页面')
    if allow_login and p.hostname in ('passport.baidu.com','wappass.baidu.com'):
        return p.scheme+'://'+p.hostname+'/'  # Never persist login query parameters.
    if p.hostname!='pan.baidu.com':raise HandoutError('BAIDU_PAGE_MISMATCH: 页面离开百度网盘分享')
    q=parse_qs(p.query)
    match=p.path.rstrip('/')=='/s/'+share_id or p.path=='/share/init' and q.get('surl')==[share_id[1:]]
    if not match:raise HandoutError('BAIDU_PAGE_MISMATCH: 当前分享身份与任务不符')
    return 'https://pan.baidu.com/s/'+share_id

def _evidence(value):
    if not isinstance(value,dict) or set(value)-{'kind','tool','reference'}:raise HandoutError('BAIDU_EVIDENCE: 只记录kind/tool/reference，不接受账号或网络凭证')
    if value.get('kind') not in ('browser_snapshot','client_snapshot','user_message'):raise HandoutError('BAIDU_EVIDENCE: 需要实际浏览器/客户端观察或用户消息')
    if any(not isinstance(value.get(k),str) or not 0<len(value[k])<=512 for k in ('tool','reference')):raise HandoutError('BAIDU_EVIDENCE: 缺少工具和实际观察引用')
    return value.copy()

def _files(items):
    if not isinstance(items,list) or len(items)>1000:raise HandoutError('BAIDU_FILES: 只记录当前分享中的有限文件列表')
    out=[];seen=set()
    for f in items:
        if not isinstance(f,dict) or set(f)-{'id','name','bytes','is_dir'}:raise HandoutError('BAIDU_FILE: 只接受id/name/bytes/is_dir')
        name=f.get('name');size=f.get('bytes')
        if not isinstance(name,str) or not name or len(name)>255 or any(c in name for c in ('/','\\','\x00','\n','\r')) or name in ('.','..'):raise HandoutError('BAIDU_FILE_NAME: 需要实际文件名，不接受路径或控制字符')
        if size is not None and (type(size) is not int or size<0):raise HandoutError('BAIDU_FILE_SIZE: 精确字节数用整数；界面仅显示约数时填null')
        if type(f.get('is_dir',False)) is not bool:raise HandoutError('BAIDU_FILE_TYPE: is_dir必须为布尔值')
        ident=f.get('id') or 'entry-'+digest([name,size,bool(f.get('is_dir'))])[:16]
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',ident) or ident in seen:raise HandoutError('BAIDU_FILE_ID: 需要唯一、可定位的文件ID')
        seen.add(ident);out.append({'id':ident,'name':name,'bytes':size,'is_dir':f.get('is_dir',False),
                                  'video':not f.get('is_dir',False) and Path(name).suffix.lower() in VIDEO_EXTENSIONS})
    return out

def _snapshot(directory):
    return {digest(p.relative_to(directory).as_posix()):[p.stat().st_size,p.stat().st_mtime_ns]
            for p in directory.rglob('*') if p.is_file() and p.resolve().is_relative_to(directory.resolve())}

def _select(job,task,ident):
    if task['status'] in ('acquired','paused') or task.get('download_started'):raise HandoutError('BAIDU_SELECTION_LOCKED: 下载开始后不更换视频；另一视频请另建任务')
    selected=next((f for f in task['files'] if f['id']==ident and f['video']),None)
    if selected is None:raise HandoutError('BAIDU_SELECTION: 请选择列表中的一个视频，不能选文件夹')
    task['selected']=selected;task['selection_digest']=digest(selected);task['download_completed']=False
    task['download_dir']='materials/incoming/'+selected['id'];directory=within(job,task['download_dir']);directory.mkdir(parents=True,exist_ok=True)
    task['baseline']=_snapshot(directory);task.pop('candidate',None)
    source=read_json(Path(job)/'source.json');source.update(video_id='baidu-'+task['share_id']+'-'+selected['id'],file_id=selected['id'],file_name=selected['name'])
    write_json(Path(job)/'source.json',source);return _save(job,task,'ready_to_download')

def select(job,ident):return _select(Path(job).resolve(),_task(job),ident)

def observe(job,observation_file):
    job=Path(job).resolve();task=_task(job);value=read_json(observation_file)
    if not isinstance(value,dict) or set(value)-{'event','observed_url','files','evidence','reason','method'}:raise HandoutError('BAIDU_OBSERVATION: 不接受未知字段、Cookie或下载签名')
    evidence=_evidence(value.get('evidence'));event=value.get('event')
    allowed={'waiting_login','waiting_extraction_code','waiting_verification','files_visible','download_started','download_completed','tool_unavailable','paused','resumed'}
    if event not in allowed:raise HandoutError('BAIDU_EVENT: 不支持此事件；完成状态只能由文件校验产生')
    if task['status']=='acquired':raise HandoutError('BAIDU_COMPLETE: 已完成的任务不重新选择或标记下载')
    if task['status']=='paused' and event not in ('resumed','paused'):raise HandoutError('BAIDU_PAUSED: 先取得用户明确继续请求')
    record={'event':event,'evidence':evidence,'at':time.time()}
    if event=='resumed':
        if evidence['kind']!='user_message' or task['status']!='paused':raise HandoutError('BAIDU_RESUME: 需要用户明确继续的消息')
        task['observations'].append(record);return _save(job,task,'downloading' if task.get('download_started') else 'awaiting_browser')
    if event in ('paused','tool_unavailable'):
        if value.get('reason') not in ('user_paused','cannot_verify_url','no_browser_tool','browser_tool_stopped','client_unavailable','other_tool_error'):
            raise HandoutError('BAIDU_REASON: 使用固定原因，不复制网页或账号信息')
        record['reason']=value['reason'];task['observations'].append(record);return _save(job,task,event)
    if evidence['kind']=='user_message':raise HandoutError('BAIDU_OBSERVATION: 用户说已登录不等于文件可读，需要实际页面观察')
    record['observed_url']=_observed_url(value.get('observed_url'),task['share_id'],event in ('waiting_login','waiting_verification'))
    if event in ('waiting_login','waiting_extraction_code','waiting_verification'):
        task['observations'].append(record);return _save(job,task,event)
    if event=='download_completed':
        if not task.get('download_started'):raise HandoutError('BAIDU_DOWNLOAD_ORDER: 尚未观察到下载开始')
        task['download_completed']=True;task['observations'].append(record)
        return _save(job,task,'checking_download')
    if event=='files_visible':
        task['files']=_files(value.get('files'));task['observations'].append(record)
        candidates=[f for f in task['files'] if f['video']]
        if task.get('download_started'):raise HandoutError('BAIDU_SELECTION_LOCKED: 已在下载，保留当前选择')
        if len(candidates)==1:return _select(job,task,candidates[0]['id'])
        return _save(job,task,'waiting_selection')
    if not task.get('selected') or task['status']!='ready_to_download':raise HandoutError('BAIDU_DOWNLOAD_ORDER: 先记录实际文件列表并选择视频')
    if value.get('method') not in ('browser_download','official_client'):raise HandoutError('BAIDU_METHOD: 使用官方网页或客户端')
    task['download_method']=value['method'];task['download_started']=True;task['observations'].append(record)
    return _save(job,task,'downloading')

def _partials(directory):
    return [p for p in directory.rglob('*') if p.is_file() and p.resolve().is_relative_to(directory.resolve()) and p.name.lower().endswith(PARTIAL_SUFFIXES)]

def _filename(name):return unicodedata.normalize('NFC',name).casefold()

def watch(job,timeout=0,stable_seconds=3):
    if not 0<=timeout<=60 or not 2<=stable_seconds<=30:raise HandoutError('BAIDU_WATCH_LIMIT: 单次等待0—60秒，稳定时间2—30秒')
    job=Path(job).resolve();deadline=time.monotonic()+timeout
    while True:
        task=_task(job)
        if task['status']=='acquired':return status_report(job,task)
        if task['status']=='paused' or not task.get('download_started'):return status_report(job,task)
        directory=within(job,task['download_dir']);selected=task['selected'];reason='file_not_found'
        files=[]
        for p in directory.rglob('*'):
            if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(directory.resolve()):continue
            if _filename(p.name)!=_filename(selected['name']) or p.suffix.lower() not in VIDEO_EXTENSIONS:continue
            st=p.stat();key=digest(p.relative_to(directory).as_posix())
            if task.get('baseline',{}).get(key)==[st.st_size,st.st_mtime_ns]:continue
            files.append(p)
        if _partials(directory):reason='partial_download_present';task.pop('candidate',None)
        elif len(files)>1:reason='multiple_candidates';task.pop('candidate',None)
        elif not files:task.pop('candidate',None)
        elif len(files)==1:
            p=files[0];st=p.stat();current={'path':p.relative_to(job).as_posix(),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
            if selected.get('bytes') is not None and st.st_size!=selected['bytes']:reason='size_mismatch';task.pop('candidate',None)
            elif st.st_size<=0:reason='empty_file';task.pop('candidate',None)
            elif selected.get('bytes') is None and not task.get('download_completed'):
                reason='awaiting_completion_confirmation';task.pop('candidate',None)
            else:
                previous=task.get('candidate',{});same=all(previous.get(k)==v for k,v in current.items())
                if same and time.time()-previous.get('first_seen',time.time())>=stable_seconds:return attach(job,p)
                task['candidate']={**current,'first_seen':previous['first_seen'] if same else time.time()};reason='awaiting_stable_file'
        task['download_progress']={'reason':reason};_save(job,task,'checking_download' if reason=='awaiting_stable_file' else 'downloading')
        if time.monotonic()>=deadline:return {**status_report(job), 'download_progress':task['download_progress']}
        time.sleep(min(1,max(0,deadline-time.monotonic())))

def attach(job,file,source_confirmed=False):
    from handout_workflow import guard_budget,failure
    if _task(job)['status']=='paused':raise HandoutError('BAIDU_PAUSED: 用户已暂停')
    guard_budget(job,'baidu_import')
    try:result=_attach(job,file,source_confirmed)
    except (HandoutError,OSError,ValueError) as error:
        failure(job,'baidu_import',error)
        task=_task(job);task['validation_error']=str(error).split(':',1)[0] if isinstance(error,HandoutError) else type(error).__name__
        _save(job,task,'validation_failed');raise
    state=read_json(Path(job)/'state.json');state.setdefault('repair_failures',{})['source']=0;write_json(Path(job)/'state.json',state)
    return result

def _attach(job,file,source_confirmed=False):
    from handout_media import media_info,run_media
    from handout_workflow import checkpoint
    job=Path(job).resolve();task=_task(job)
    if task['status']=='paused':raise HandoutError('BAIDU_PAUSED: 用户已暂停')
    source_file=Path(file).resolve()
    if not source_file.is_file() or source_file.suffix.lower() not in VIDEO_EXTENSIONS or source_file.name.lower().endswith(PARTIAL_SUFFIXES):raise HandoutError('BAIDU_VIDEO: 需要已完成的视频文件')
    partials=[p for p in source_file.parent.iterdir() if p.is_file() and p.name.lower().endswith(PARTIAL_SUFFIXES)
              and p.name.lstrip('.').casefold().startswith(source_file.name.casefold())]
    if partials:raise HandoutError('BAIDU_PARTIAL: 该视频仍有下载临时文件，先确认下载完成')
    selected=task.get('selected')
    if not selected and not source_confirmed:raise HandoutError('BAIDU_SOURCE_CONFIRMATION: 没有页面选择记录，需用户明确确认此本地文件来自该分享')
    renamed=bool(selected and _filename(source_file.name)!=_filename(selected['name']))
    if renamed and not source_confirmed:raise HandoutError('BAIDU_FILENAME_MISMATCH: 文件名与选择记录不符，需确认是否下载时改名')
    if selected and selected.get('bytes') is None and not task.get('download_completed') and not source_confirmed:
        raise HandoutError('BAIDU_COMPLETION_CONFIRMATION: 未知精确大小，先观察官方下载完成或由用户确认完整文件')
    before=source_file.stat()
    if selected and selected.get('bytes') is not None and selected['bytes']!=before.st_size:raise HandoutError('BAIDU_SIZE_MISMATCH: 文件大小与所选视频不符')
    if not before.st_size:raise HandoutError('BAIDU_EMPTY: 视频为空')
    detected=media_info(source_file)
    if not detected['video'] or detected['duration']<=0:raise HandoutError('BAIDU_VIDEO: 没有可用视频轨或时长')
    frame=run_media(['-v','error','-i',str(source_file),'-map','0:v:0','-frames:v','1','-vf','scale=2:2','-pix_fmt','rgb24','-f','rawvideo','-'])
    if len(frame.stdout)!=12:raise HandoutError('BAIDU_DECODE: 未能实际解码首帧')
    checksum=file_hash(source_file);source=read_json(job/'source.json')
    if source.get('media_sha256') and source['media_sha256']!=checksum:raise HandoutError('BAIDU_DIFFERENT_VIDEO: 任务已有不同视频，另建任务避免混用证据')
    if task['status']=='acquired' and status_report(job,task).get('media_current'):return {**status_report(job,task),'cached':True}
    if source_file.is_relative_to(job):target=source_file
    else:
        target=within(job,'materials/video'+source_file.suffix.lower());temp=target.with_suffix(target.suffix+'.importing')
        if temp.exists() or temp.is_symlink():raise HandoutError('BAIDU_IMPORT_BUSY: 临时导入文件已存在，先检查旧任务')
        if target.exists() and not source.get('media_sha256') and file_hash(target)!=checksum:raise HandoutError('BAIDU_TARGET_EXISTS: 目标已有不同文件，不覆盖')
        shutil.copyfile(source_file,temp)
        if file_hash(temp)!=checksum:temp.unlink(missing_ok=True);raise HandoutError('BAIDU_COPY_CHANGED: 拷贝未完成，原文件保留')
        os.replace(temp,target)
    after=source_file.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise HandoutError('BAIDU_FILE_CHANGED: 校验期间文件仍在变化，继续等待')
    source.update(media_path=target.relative_to(job).as_posix(),duration=detected['duration'],media_sha256=checksum,acquisition_method=task.get('download_method','explicit_local_import'))
    write_json(job/'source.json',source)
    receipt={'media_path':source['media_path'],'sha256':checksum,'bytes':before.st_size,'duration':detected['duration'],'has_audio':detected['audio'],
             'video_track':True,'first_frame_decoded':True,'decode_scope':'first_frame','selection_digest':task.get('selection_digest'),
             'completion_basis':'exact_selected_bytes' if selected and selected.get('bytes') is not None else 'host_observed_completion' if task.get('download_completed') else 'user_confirmed_file',
             'source_assurance':'host_confirmed_download_with_rename' if renamed else 'host_observed_share_and_selection' if selected else 'user_confirmed_local_file',
             'checker_sha256':file_hash(__file__),'validated_at':time.time()}
    write_json(job/'acquisition/baidu-receipt.json',receipt);task['receipt']=receipt
    task['download_progress']={'reason':'local_video_validated'};task.pop('validation_error',None)
    _save(job,task,'acquired');checkpoint(job,'baidu_video',[source['media_path'],'source.json','acquisition/baidu-receipt.json'],task['next_action'])
    return status_report(job,task)
