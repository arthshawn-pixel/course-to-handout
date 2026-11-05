"""Student projection: semantic blocks, quiet provenance and separate processing report."""
from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
from pathlib import Path

from handout_core import HandoutError,read_json,write_json,within,file_hash,stamp,source_link,stage,digest
from handout_v2 import validate_v2,code_digest
from handout_text import text_tex,claim_tex
from handout_figures import crop_figure


def segment_label(source,part):
    return '网盘视频' if source.get('provider')=='baidu' else f'P{part}'


def merged_ranges(unit,gap=2):
    result=[]
    for ref in sorted(unit.get('sources',[]),key=lambda r:(r['video_id'],r['part'],r['start'])):
        if result and (result[-1]['video_id'],result[-1]['part'])==(ref['video_id'],ref['part']) and ref['start']<=result[-1]['end']+gap:
            result[-1]['end']=max(result[-1]['end'],ref['end'])
        else:result.append({k:ref[k] for k in ('video_id','part','start','end')})
    return result


def font_setup(build,root,fonts,math_font='stix2'):
    from handout_notation import font_inventory
    inventory=font_inventory(root)
    if inventory['missing']:raise HandoutError('FONT_FILES_MISSING: '+', '.join(inventory['missing']))
    (build/'fonts').mkdir(exist_ok=True)
    for name in inventory['required']:
        if name!='SourceHanSerifSC-Regular.otf' or fonts=='sourcehan':shutil.copyfile(root/'assets/fonts'/name,build/'fonts'/name)
    selected={'stix2':'STIXTwoMath-Regular.otf','termes':'texgyretermes-math.otf'}[math_font]
    value=r'\setmainfont{texgyretermes-regular.otf}[Path=fonts/,BoldFont=texgyretermes-bold.otf,ItalicFont=texgyretermes-italic.otf,BoldItalicFont=texgyretermes-bolditalic.otf]'+'\n'+r'\setmathfont{'+selected+r'}[Path=fonts/]'+'\n'
    if fonts=='sourcehan':
        return value+r'\setCJKmainfont{SourceHanSerifSC-Regular.otf}[Path=fonts/,AutoFakeBold=2]'
    return value+r'\setCJKmainfont{SimSun}[AutoFakeBold=2]'


def compile_tex(build,engine,executable,cache,timeout=300):
    from handout_workflow import run_tool
    env=os.environ.copy();env.update(openin_any='p',openout_any='p',shell_escape='f')
    env.setdefault('TECTONIC_CACHE_DIR',str(cache))
    args=[executable,'--untrusted','--keep-intermediates','--keep-logs','lecture.tex'] if engine=='tectonic' else [executable,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','lecture.tex']
    logs=[]
    for _ in range(1 if engine=='tectonic' else 3):
        try:p=run_tool(args,cwd=build,env=env,capture_output=True,timeout=timeout)
        except subprocess.TimeoutExpired as e:
            (build/'compiler.log').write_text((e.stdout or b'').decode('utf-8',errors='replace')+(e.stderr or b'').decode('utf-8',errors='replace'),encoding='utf-8')
            raise HandoutError('TEX_TIMEOUT: 当前阶段超时；首次宏包预热与正文编译应分开，缓存已保留') from e
        logs.append(p.stdout.decode('utf-8',errors='replace')+p.stderr.decode('utf-8',errors='replace'))
        (build/'compiler.log').write_text('\n'.join(logs),encoding='utf-8')
        if p.returncode:raise HandoutError('TEX_FAILED: 见当前 build 目录 compiler.log；只修复排版阶段')
    if (build/'lecture.log').exists():logs.append((build/'lecture.log').read_text(encoding='utf-8',errors='replace'))
    return '\n'.join(logs)


def inspect_pdf(pdf,log,aux,figure_tags):
    from pypdf import PdfReader
    reader=PdfReader(pdf);warnings=sorted(set(line for line in log.splitlines() if any(w in line for w in ('Missing character','Overfull','undefined references'))))
    labels=dict(re.findall(r'\\newlabel\{([^}]+)\}\{\{[^}]*\}\{(\d+)\}',aux))
    caption_pages={tag:{'image':labels.get('image:'+tag),'caption':labels.get('caption:'+tag)} for tag in figure_tags}
    if any(not v['image'] or v['image']!=v['caption'] for v in caption_pages.values()):warnings.append('FIGURE_CAPTION_PAGE_MISMATCH')
    fonts=[]
    for page in reader.pages:
        for name,ref in page.get('/Resources',{}).get('/Font',{}).items():
            font=ref.get_object();children=font.get('/DescendantFonts') or [font]
            for child in children:
                child=child.get_object();descriptor=child.get('/FontDescriptor')
                if descriptor:
                    descriptor=descriptor.get_object();embedded=any(k in descriptor for k in ('/FontFile','/FontFile2','/FontFile3'))
                    fonts.append({'font':str(font.get('/BaseFont',name)),'embedded':embedded})
                    if not embedded:warnings.append('FONT_NOT_EMBEDDED: '+str(name))
    return {'pages':len(reader.pages),'warnings':sorted(set(warnings)),'fonts':fonts,'figure_caption_pages':caption_pages,
            'visual_review':'pending','notice':'结构化页码/字体/日志检查已执行；仍须实际查看全篇概览与高风险页面。'},labels


def render_student(job,layout='single',draft=False,engine='xelatex',fonts='sourcehan',mode='reading',accent='blue',margin=20):
    from handout_render import engine_path,ROOT
    from handout_workflow import runtime_fingerprint,checkpoint
    if layout!='single':raise HandoutError('V2_LAYOUT_DEFERRED: 本版按改版需求先稳定 A4 单栏；不静默套用旧双栏模板')
    if mode not in ('reading','writing') or accent not in ('blue','slate') or not 18<=margin<=22:raise HandoutError('版式参数无效')
    job=Path(job).resolve();doc=read_json(job/'handout.json');source=read_json(job/'source.json')
    subtitles=read_json(job/'materials/subtitles.json');frames=read_json(job/'materials/frames.json')
    validation=validate_v2(doc,source,subtitles,frames,job);write_json(job/'validation.json',validation)
    if not validation['valid']:raise HandoutError('V2_VALIDATION_FAILED: 见 validation.json 中单元、字段路径和预期条件')
    if not draft and not validation['release_ready']:raise HandoutError('CONTENT_REVIEW_PENDING: 存在未完成/过期核验，仅可用 --draft 导出校对稿')
    executable=engine_path(engine);template=ROOT/'templates/student.tex';build=job/'build'/('student-'+mode);build.mkdir(parents=True,exist_ok=True)
    profile=runtime_fingerprint(engine,fonts)
    figures={f['id']:f for f in doc.get('figures',[])}
    frame_map={f['id']:f for f in frames}
    embedded={b['figure_id'] for u in doc['units'] for group in [u['body'],u['conclusion'],*[s['content'] for s in u.get('steps',[])]] for b in group if b['type']=='image'}
    image_hashes={fid:file_hash(within(job,frame_map[figures[fid]['frame_id']]['path'])) for fid in embedded}
    fingerprint={'content':doc,'source':source,'template':file_hash(template),'program':code_digest(ROOT/'scripts'),
                 'runtime':profile,'images':image_hashes,'parameters':[layout,mode,accent,margin,draft]}
    def action():
        for suffix in ('.aux','.out','.toc','.log','.pdf'):(build/('lecture'+suffix)).unlink(missing_ok=True)
        paths={fid:crop_figure(job,figures[fid],frames,build/'figures').relative_to(build).as_posix() for fid in embedded}
        tags={fid:digest(fid)[:16] for fid in embedded}
        def blocks(items):
            result=[]
            for b in items:
                kind=b['type']
                if kind=='text':result.append(text_tex(b['text'])+'\n\n')
                elif kind=='math':result.append('\\[\n'+b['latex']+'\n\\]\n')
                elif kind in ('chem','quantity'):
                    from handout_notation import notation_tex
                    result.append('\\[\n'+notation_tex(b)+'\n\\]\n')
                elif kind in ('sequence','coin_recurrence','partition'):result.append('\\[\n'+claim_tex(b)+'\n\\]\n')
                elif kind=='table':
                    def cell(c):return r'\('+c['math']+r'\)' if isinstance(c,dict) else text_tex(c)
                    width=.94/len(b['columns']);spec=''.join('p{'+f'{width:.3f}'+r'\linewidth}' for _ in b['columns'])
                    result.append(r'\par\smallskip\begin{tabular}{@{}'+spec+r'@{}}\toprule'+'\n')
                    for row in [b['columns'],*b['rows']]:result.append(' & '.join(cell(c) for c in row)+r'\\'+'\n'+(r'\midrule'+'\n' if row is b['columns'] else ''))
                    result.append(r'\bottomrule\end{tabular}\par\smallskip'+'\n')
                elif kind=='image':
                    fid=b['figure_id'];fig=figures[fid];frame=frame_map[fig['frame_id']];tag=tags[fid]
                    caption=b.get('caption',fig.get('caption','原课板书局部'))+f"（{segment_label(source,source['part'])} {stamp(frame['time'])}）"
                    result.append(r'\par\smallskip\noindent\begin{minipage}{\linewidth}\centering'+'\n'+r'\label{image:'+tag+'}\n'+
                        r'\includegraphics[width=.84\linewidth,height=.28\textheight,keepaspectratio]{'+paths[fid]+'}\\par\n'+r'\label{caption:'+tag+'}{\\small '+text_tex(caption)+r'}\par\end{minipage}'+'\n')
            return ''.join(result)
        def references(u):
            parts=[]
            for r in merged_ranges(u):
                label=f"原视频 {segment_label(source,r['part'])} {stamp(r['start'])} - {stamp(r['end'])}"
                link=source_link(source,r['start']);parts.append(r'\href{'+text_tex(link)+'}{'+text_tex(label)+'}' if link else text_tex(label))
            return r'\par{\small\color{ink!75}'+r'\quad '.join(parts)+'}\\par\n' if parts else ''
        def unit(u,answer=False):
            pieces=[]
            pieces.append(r'\markright{'+text_tex(('解析：' if answer else '')+u['title'][:12])+'}\n')
            label=r'\label{unit:'+u['id']+'}\n' if not answer else ''
            if u['type'] in ('definition','theorem') and not answer:
                pieces.extend([r'\begin{knowledgebox}{'+text_tex(u['title'])+'}\n',label,blocks(u['body']),blocks(u['conclusion']),r'\end{knowledgebox}'+'\n'])
            else:
                pieces.append(r'\teachingtitle{'+text_tex(('解析：' if answer else '')+u['title'])+'}\n')
                pieces.append(label)
                if not answer:
                    if u['type'] in ('example','exercise'):pieces.append(r'\begin{questionbox}'+blocks(u['body'])+r'\end{questionbox}'+'\n')
                    else:pieces.append(blocks(u['body']))
                if u['type']!='exercise' or answer:
                    if u.get('answer_origin')=='ai_supplement':pieces.append('补充解答：原视频仅展示题目。\\par\n')
                    if u.get('motivation'):pieces.append(text_tex(u['motivation'])+'\n\n')
                    for i,s in enumerate(u.get('steps',[]),1):
                        if s.get('heading'):pieces.append(r'\stagetitle{'+text_tex(s['heading'])+'}\n')
                        pieces.append(blocks(s['content']))
                        if s.get('show_reason') and s.get('basis'):pieces.append(text_tex(s['basis'])+'\n\n')
                    if u['conclusion']:pieces.append(r'\begin{knowledgebox}{结果}'+blocks(u['conclusion'])+r'\end{knowledgebox}'+'\n')
                    if u['pitfalls']:pieces.append(r'\par{\small '+text_tex('提醒：'+'；'.join(u['pitfalls']))+'}\\par\n')
                elif mode=='writing':pieces.append(r'\vspace{18mm}'+'\n')
            if not answer:pieces.append(references(u))
            if u['review']['status']=='insufficient':pieces.append(r'\par\textbf{待核对：'+text_tex(u['review']['reason'])+'}\\par\n')
            failed=[i for i in validation['issues'] if i.get('unit_id')==u['id'] and i.get('dimension') in ('calculation','proof') and i.get('code')=='CHECK_INVALID']
            if failed:pieces.append(r'\par\textbf{本题解答存在尚未解决的核验问题，请勿作为确定结论使用。}\par'+'\n')
            return ''.join(pieces)
        content=[]
        for section in doc['sections']:
            selected=[u for u in doc['units'] if u['section_id']==section['id'] and u['type']!='exercise']
            if selected:
                if len(selected)!=1 or selected[0]['title']!=section['title']:
                    content.append(r'\teachingtitle{'+text_tex(section['title'])+'}\n')
                for u in selected:content.append(unit(u))
        exercises=[u for u in doc['units'] if u['type']=='exercise']
        if exercises:
            content.append(r'\section*{自测练习}'+'\n配套新题和改编题在此集中练习；原课留练题单独注明。\\par\n')
            for u in exercises:
                if u['origin']=='course':content.append('原课留练：\\par\n')
                content.append(unit(u))
            content.append(r'\clearpage\section*{自测答案与解析}'+'\n')
            for u in exercises:content.append(unit(u,True))
        index=[]
        for u in doc['units']:
            ranges=merged_ranges(u)
            if not ranges:continue
            labels=[]
            for r in ranges:
                t=f"{segment_label(source,r['part'])} {stamp(r['start'])} - {stamp(r['end'])}";url=source_link(source,r['start'])
                labels.append(r'\href{'+text_tex(url)+'}{'+text_tex(t)+'}' if url else text_tex(t))
            index.append(text_tex(u['title'])+r' & \pageref{unit:'+u['id']+'} & '+r'\newline '.join(labels)+r'\\'+'\n')
        intro=[text_tex(doc['level']), '先修：'+text_tex('；'.join(doc['prerequisites'])) if doc['prerequisites'] else '',
               text_tex(doc.get('learning_goal','')),text_tex('课程来源：'+source['title'])]
        if draft:intro.insert(0,r'{\small 校对稿}')
        values={'MARGIN':str(margin),'FONTS':font_setup(build,ROOT,fonts,doc.get('typography',{}).get('math_font','stix2')),'ACCENT':'29495C' if accent=='blue' else '3A4854',
                'HEADER':text_tex(doc.get('short_title',doc['title'][:20])),'TITLE':text_tex(doc['title']),
                'INTRO':'\\par\n'.join(x for x in intro if x)+'\\par\n','BODY':''.join(content),'INDEX':''.join(index)}
        source_heading='文件与时间' if source.get('provider')=='baidu' else '分P与时间'
        values['SOURCEINDEX']=(r'\Needspace{10\baselineskip}\section*{原视频定位}'+'\n'+r'\begin{longtable}{@{}p{.47\textwidth}r p{.32\textwidth}@{}}'+'\n'+r'\toprule 内容 & 页码 & '+source_heading+r'\\\midrule\endhead'+'\n'+''.join(index)+r'\bottomrule\end{longtable}') if index else ''
        tex=re.sub(r'@@([A-Z]+)@@',lambda m:values[m[1]],template.read_text(encoding='utf-8'))
        (build/'lecture.tex').write_text(tex,encoding='utf-8')
        shared_cache=Path(os.environ.get('HANDOUT_RUNTIME',job.parent/'handout-runtime'))/'tex-cache'
        log=compile_tex(build,engine,executable,shared_cache,timeout=int(os.environ.get('HANDOUT_TEX_TIMEOUT','300')))
        aux=(build/'lecture.aux').read_text(encoding='utf-8');audit,labels=inspect_pdf(build/'lecture.pdf',log,aux,list(tags.values()))
        write_json(build/'layout-report.json',audit)
        if audit['warnings'] and not draft:raise HandoutError('PDF_AUDIT_FAILED: 正式导出发现缺字、溢出、字体或图注问题')
        dest=job/'deliverables';dest.mkdir(exist_ok=True);stem='handout-single'+('-writing' if mode=='writing' else '')+('-draft' if draft else '')
        pdf=dest/(stem+'.pdf');shutil.copyfile(build/'lecture.pdf',pdf)
        index_path=dest/(stem+'-source-index.csv')
        with index_path.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['内容','讲义页码','文件' if source.get('provider')=='baidu' else '分P','开始','结束','链接'])
            for u in doc['units']:
                if 'unit:'+u['id'] not in labels:raise HandoutError('PAGE_LABEL_MISSING: '+u['id'])
                for r in merged_ranges(u):
                    title="'"+u['title'] if u['title'].lstrip().startswith(('=','+','-','@')) else u['title']
                    writer.writerow([title,labels['unit:'+u['id']],source.get('file_name','网盘视频') if source.get('provider')=='baidu' else r['part'],stamp(r['start']),stamp(r['end']),source_link(source,r['start'])])
        report=dest/(stem+'-processing-report.json')
        write_json(report,{'protocol':2,'pdf_sha256':file_hash(pdf),'render_fingerprint':digest(fingerprint),'coverage':doc.get('coverage'), 'validation':validation,'figure_decisions':doc.get('figures',[]),
                    'unit_checks':{u['id']:{'review':u['review'],'checks':u.get('checks',{})} for u in doc['units']},
                    'runtime':profile,'pdf_audit':audit,'student_projection':'元信息与核验记录不逐项渲染；未解决内容保留校对稿标识',
                    'metrics':read_json(job/'metrics.json') if (job/'metrics.json').exists() else {}})
        return [pdf,index_path,report,build/'lecture.tex',build/'layout-report.json']
    result=stage(job,'render_v2_'+mode+('_draft' if draft else ''),fingerprint,action)
    checkpoint(job,'pdf_'+mode,[str((job/'deliverables'/('handout-single'+('-writing' if mode=='writing' else '')+('-draft' if draft else '')+'.pdf')).relative_to(job))],'render')
    return result
