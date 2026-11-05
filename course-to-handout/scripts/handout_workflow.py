"""Checkpoints, bounded repairs, metrics and reusable runtime preparation."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import importlib.metadata
from pathlib import Path

from handout_core import HandoutError, read_json, write_json, file_hash, digest, within

DEFAULT_BUDGETS={'network':2,'structure':3,'source':3,'render':3}


def run_tool(args,**kwargs):
    started=time.monotonic();job=os.environ.get('HANDOUT_JOB');result=None
    try:
        result=subprocess.run(args,**kwargs);return result
    finally:
        if job and (Path(job)/'state.json').exists():
            metric(job,'subprocess',tool=Path(str(args[0])).name,wall_seconds=time.monotonic()-started,
                   return_code=result.returncode if result is not None else None)


def settings(job):
    path=Path(job)/'config.json'
    return read_json(path) if path.exists() else {'repair_budgets':DEFAULT_BUDGETS.copy()}


def category(name):
    return 'network' if name.startswith('fetch') else 'render' if name.startswith(('render','warmup')) else 'source' if name.startswith(('frame','audio','subtitles','baidu_import')) else 'structure'


def guard_budget(job,name):
    state=read_json(Path(job)/'state.json');cat=category(name); count=state.get('repair_failures',{}).get(cat,0)
    budget=settings(job).get('repair_budgets',{}).get(cat,DEFAULT_BUDGETS[cat])
    if count>=budget: raise HandoutError(f'REPAIR_BUDGET_EXHAUSTED: {cat} 连续失败 {count} 次，停止自动修复；检查 diagnostics 后再决定下一步')


def failure(job,name,error):
    state=read_json(Path(job)/'state.json');cat=category(name)
    state.setdefault('repair_failures',{})[cat]=state.get('repair_failures',{}).get(cat,0)+1
    write_json(Path(job)/'state.json',state)
    write_json(Path(job)/'diagnostics'/f'{name}.json',{'stage':name,'category':cat,'error_type':type(error).__name__,
               'message':str(error) if isinstance(error,HandoutError) else '检查输入和阶段日志；未回传未知异常原文','next_action':'修复当前阶段或提交可定位诊断；不要临时复制整份渲染器'})


def metric(job,event,**data):
    job=Path(job);path=job/'metrics.json'
    metrics=read_json(path) if path.exists() else {'events':[],'host_model_calls':None,'host_tool_calls':None,'human_interventions':None,'analysed_frames':None}
    metrics['events'].append({'event':event,'at':time.time(),**data})
    write_json(path,metrics)


def checkpoint(job,name,outputs,next_action):
    job=Path(job);path=job/'checkpoints.json';current=read_json(path) if path.exists() else {}
    current[name]={'outputs':{str(p):file_hash(within(job,p)) for p in outputs},'next_action':next_action,'saved':time.time()}
    write_json(path,current)


def resume(job):
    job=Path(job);state=read_json(job/'state.json');path=job/'checkpoints.json';points=read_json(path) if path.exists() else {}
    result={'valid_checkpoints':[],'stale_checkpoints':[],'stages':{},'next_actions':[]}
    for name,cp in points.items():
        valid=all(within(job,p).is_file() and file_hash(within(job,p))==h for p,h in cp['outputs'].items())
        result['valid_checkpoints' if valid else 'stale_checkpoints'].append(name)
        if not valid: result['next_actions'].append(cp['next_action'])
    for name,s in state.get('stages',{}).items():
        valid=s.get('status')=='done' and all(within(job,p).is_file() and file_hash(within(job,p))==h for p,h in s.get('outputs',{}).items())
        result['stages'][name]='valid' if valid else 'stale' if s.get('status')=='done' else s.get('status','unknown')
    if (job/'handout.json').exists():
        from handout_v2 import validate_v2
        doc=read_json(job/'handout.json')
        if doc.get('schema_version')==2:
            check=validate_v2(doc,read_json(job/'source.json'),read_json(job/'materials/subtitles.json'),read_json(job/'materials/frames.json'),job)
            result['current_validation']=check
            if not check['valid'] or check['issues']:result['next_actions'].append('check：只修复所列单元与字段')
    if state.get('resource_access',{}).get('subtitles',{}).get('status')=='waiting_login' and not read_json(job/'materials/subtitles.json'):
        result['next_actions'].append('等待用户在任务浏览器登录后验证字幕；不轮询')
    if (job/'acquisition/baidu.json').exists():
        from handout_baidu import status_report
        acquisition=status_report(job);result['acquisition']=acquisition
        result['next_actions'].append(acquisition['next_action'])
    result['next_actions']=list(dict.fromkeys(result['next_actions'])) or ['复用有效材料，继续下一个教学单元或执行 render']
    result['metrics']=read_json(job/'metrics.json') if (job/'metrics.json').exists() else {}
    return result


def runtime_fingerprint(engine,fonts):
    from handout_render import engine_path, ROOT
    executable=engine_path(engine)
    run=run_tool([executable,'--version'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
    dependencies={}
    for name in ('Pillow','pypdf','PyYAML','imageio-ffmpeg','yt-dlp'):
        try:dependencies[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:dependencies[name]='unavailable'
    return {'os':platform.system(),'architecture':platform.machine(),'python':platform.python_version(),'dependencies':dependencies,'engine':engine,'version':run.stdout.splitlines()[0] if run.stdout else 'unknown',
            'executable_hash':file_hash(executable),'font':file_hash(ROOT/'assets/fonts/SourceHanSerifSC-Regular.otf') if fonts=='sourcehan' else 'system-SimSun',
            'academic_fonts':{p.name:file_hash(p) for p in sorted((ROOT/'assets/fonts').glob('*.otf'))}}


def preflight(runtime,engine='tectonic',fonts='sourcehan'):
    """Actually run media, subtitle and a long-frame/caption PDF smoke fixture."""
    from handout_media import ffmpeg_path,run_media,media_info
    from handout_core import parse_subtitles
    from handout_v2 import minimal_unit
    from handout_render import render
    runtime=Path(runtime).resolve();runtime.mkdir(parents=True,exist_ok=True)
    fingerprint=runtime_fingerprint(engine,fonts)
    from handout_render import ROOT
    from handout_v2 import code_digest
    fingerprint['render_program']=code_digest(ROOT/'scripts')
    fingerprint['template']=file_hash(ROOT/'templates/student.tex')
    cache=runtime/'capabilities.json'
    if cache.exists():
        prior=read_json(cache)
        pdf=runtime/'smoke/deliverables/handout-single-draft.pdf'
        if prior.get('fingerprint')==fingerprint and pdf.exists() and prior.get('pdf_hash')==file_hash(pdf): return {**prior,'cached':True}
    started=time.time();job=runtime/'smoke';(job/'materials').mkdir(parents=True,exist_ok=True)
    write_json(job/'state.json',{'stages':{},'access':{'status':'ready'}})
    os.environ['HANDOUT_JOB']=str(job)
    video=job/'materials/smoke.mp4'
    run_media(['-y','-f','lavfi','-i','color=c=white:s=640x360:r=1','-f','lavfi','-i','anullsrc=r=16000:cl=mono','-t','2','-c:v','libx264','-c:a','aac',str(video)])
    media=media_info(video); image=job/'materials/figure.png'
    run_media(['-y','-i',str(video),'-frames:v','1',str(image)])
    sub=job/'materials/smoke.srt';sub.write_text('1\n00:00:00,000 --> 00:00:01,500\n中文 English 数学字体小样\n',encoding='utf-8')
    parsed=parse_subtitles(sub);write_json(job/'materials/subtitles.json',parsed)
    write_json(job/'source.json',{'title':'环境预热与版式回归','level':'开发小样','duration':2,'video_id':'smoke','part':1,'url':'','fixture':True})
    write_json(job/'materials/frames.json',[{'id':'f1','time':1,'path':'materials/figure.png','video_id':'smoke','part':1}])
    u=minimal_unit('smoke','c1');u.update(title='中文 English 数学与跨页知识框',type='theorem',conditions=['用于字体与分页检查'],
       body=[{'type':'text','text':'中文宋体与英文 Roman I / Ⅰ；数学符号 ≤ ≥ ≠ ∈ ∞，上下标 x₀²。'},
             {'type':'math','latex':r'\begin{aligned}a_{n+1}&=\lambda a_n+\mu,\\a_n&=s+(a_1-s)\lambda^{n-1}\end{aligned}'},
             {'type':'math','latex':r'\nabla\cdot\mathbf{E}=\rho/\varepsilon_0,\quad \mathbb{R}^n,\quad\hbar\omega'},
             {'type':'chem','formula':'2 H2 + O2 -> 2 H2O'},
             {'type':'quantity','value':'9.81','unit':r'\metre\per\second\squared'},
             *[{'type':'text','text':'这是较长的知识框内容，用于检查语义块能否自然跨页，正文和图注不应相互分离。'} for _ in range(42)]],
       conclusion=[{'type':'image','figure_id':'fig1','caption':'带图注的最小图片，环境回归小样'}],
       sources=[{'video_id':'smoke','part':1,'start':0,'end':2}],evidence=[{'kind':'frame','id':'f1','relation':'same_board','reason':'测试图片与图注关联'}])
    doc={'schema_version':2,'title':'环境与版式小样','level':'开发','prerequisites':[],'learning_goal':'','coverage':{'included':['最小回归'],'omitted':[]},
         'sections':[{'id':'c1','title':'字体、长框与图注','start':0,'end':2,'origin':'human'}],'units':[u],
         'figures':[{'id':'fig1','unit_id':'smoke','frame_id':'f1','decision':'embed','reason':'验证图注不分离','crop':None}]}
    write_json(job/'handout.json',doc)
    os.environ.setdefault('TECTONIC_CACHE_DIR',str(runtime/'tex-cache'))
    previous_timeout=os.environ.get('HANDOUT_TEX_TIMEOUT')
    os.environ['HANDOUT_TEX_TIMEOUT']=os.environ.get('HANDOUT_WARMUP_TIMEOUT','900')
    try:render(job,'single',True,engine,fonts)
    finally:
        if previous_timeout is None:os.environ.pop('HANDOUT_TEX_TIMEOUT',None)
        else:os.environ['HANDOUT_TEX_TIMEOUT']=previous_timeout
    audit=read_json(job/'build/student-reading/layout-report.json')
    if audit['warnings']:raise HandoutError('PREFLIGHT_FONT_AUDIT_FAILED: 小样存在缺字、溢出或图注问题，暂不能宣称环境就绪')
    pdf=job/'deliverables/handout-single-draft.pdf'
    result={'fingerprint':fingerprint,'media':media,'subtitles':'passed','pdf_compile':'passed','visual_review':'pending',
            'pdf_hash':file_hash(pdf),'wall_seconds':time.time()-started,'phase':'installation_warmup','cached':False,
            'browser':'host_check_required','asr':'not_bundled'}
    write_json(cache,result);return result
