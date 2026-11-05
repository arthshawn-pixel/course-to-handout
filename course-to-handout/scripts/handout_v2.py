"""v2 content contract, diagnostics, evidence relations and local unit operations."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from handout_core import HandoutError, read_json, write_json, digest, file_hash, within, number, interval, validate_math

PROTOCOL = 2
DIMENSIONS = ('fidelity', 'calculation', 'proof')
RELATIONS = ('same_board', 'recap', 'residual', 'audio', 'external_reference')


def content_digest(unit,figures=None):
    """Editorial presentation and review records do not change mathematical content."""
    excluded = {'review', 'checks', 'wide', 'display', 'layout', '_fragment', '_step_offset'}
    value={k:v for k,v in unit.items() if k not in excluded}
    relevant=[f for f in (figures or []) if f.get('unit_id')==unit.get('id')]
    return digest({'unit':value,'figures':relevant}) if relevant else digest(value)


def code_digest(root, extensions=('.py','.js')):
    root = Path(root)
    return digest({p.relative_to(root).as_posix():file_hash(p) for p in sorted(root.rglob('*'))
                   if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts})


def diagnostic(code, unit, path, value, expected, evidence=None):
    return {'code':code, 'unit_id':unit, 'path':path, 'value':value, 'expected':expected, 'evidence':evidence}


def validate_v2(doc, source, subtitles, frames, root):
    errors, issues = [], []
    def fail(code, ident, path, value, expected, evidence=None):
        errors.append(diagnostic(code,ident,path,value,expected,evidence))
    def text(x): return isinstance(x,str) and bool(x.strip())
    if not isinstance(doc,dict):
        return {'valid':False,'errors':[diagnostic('DOCUMENT_TYPE',None,'$',type(doc).__name__,'object')],'issues':[],'release_ready':False}
    if doc.get('schema_version') != 2: fail('PROTOCOL',None,'schema_version',doc.get('schema_version'),2)
    for k in ('title','level'):
        if not text(doc.get(k)): fail('REQUIRED',None,k,doc.get(k),'non-empty text')
    for k in ('sections','units','prerequisites'):
        if not isinstance(doc.get(k),list): fail('TYPE',None,k,type(doc.get(k)).__name__,'array')
    if not isinstance(doc.get('figures',[]),list):fail('TYPE',None,'figures',type(doc.get('figures')).__name__,'array')
    typography=doc.get('typography',{})
    if not isinstance(typography,dict) or typography.get('math_font','stix2') not in ('stix2','termes'):
        fail('FONT_PROFILE',None,'typography',typography,'math_font: stix2 or termes')
    if errors: return {'valid':False,'errors':errors,'issues':[],'release_ready':False}
    duration=source['duration']; smap={s['id']:s for s in subtitles}; fmap={f['id']:f for f in frames}
    sections={}; ids=set(); figure_ids=set(); figures={}
    for i,s in enumerate(doc['sections']):
        if not isinstance(s,dict) or not isinstance(s.get('id'),str):
            fail('SECTION',None,f'sections[{i}]',s,'object with id');continue
        if s['id'] in sections: fail('DUPLICATE',None,f'sections[{i}].id',s['id'],'unique id')
        sections[s['id']]=s
        if not text(s.get('title')):fail('REQUIRED',None,f'sections[{i}].title',s.get('title'),'non-empty section title')
        if not interval(s.get('start'),s.get('end'),duration): fail('TIME_RANGE',None,f'sections[{i}]',s,'0 <= start < end <= duration')
    for i,fig in enumerate(doc.get('figures',[])):
        if not isinstance(fig,dict) or not isinstance(fig.get('id'),str):
            fail('FIGURE',None,f'figures[{i}]',fig,'figure decision object');continue
        ident=fig['id']; figures[ident]=fig
        if ident in figure_ids: fail('DUPLICATE',fig.get('unit_id'),f'figures[{i}].id',ident,'unique id')
        figure_ids.add(ident)
        if not isinstance(fig.get('frame_id'),str) or fig.get('frame_id') not in fmap: fail('FRAME_MISSING',fig.get('unit_id'),f'figures[{i}].frame_id',fig.get('frame_id'),'registered frame','materials/frames.json')
        if fig.get('decision') not in ('embed','evidence_only','omit_duplicate'): fail('FIGURE_DECISION',fig.get('unit_id'),f'figures[{i}].decision',fig.get('decision'),'embed/evidence_only/omit_duplicate')
        if not text(fig.get('reason')): fail('FIGURE_PURPOSE',fig.get('unit_id'),f'figures[{i}].reason',None,'specific information value or coverage explanation')
        if fig.get('decision') == 'omit_duplicate' and not fig.get('covered_by'): fail('FIGURE_REPLACEMENT',fig.get('unit_id'),f'figures[{i}]',ident,'covering frame or content unit')
        crop=fig.get('crop')
        if crop is not None and (not isinstance(crop,list) or len(crop)!=4 or not all(type(v) is int for v in crop) or min(crop)<0 or crop[2]<=0 or crop[3]<=0):
            fail('CROP',fig.get('unit_id'),f'figures[{i}].crop',crop,'[x,y,width,height] in original image pixels')
    def blocks(items, ident, path):
        if not isinstance(items,list): fail('BLOCKS',ident,path,type(items).__name__,'array');return
        for j,b in enumerate(items):
            p=f'{path}[{j}]'
            if not isinstance(b,dict): fail('BLOCK',ident,p,b,'typed block');continue
            kind=b.get('type')
            if kind=='text':
                if not text(b.get('text')): fail('TEXT',ident,p,b,'non-empty text')
            elif kind=='math':
                try: validate_math(b.get('latex'))
                except HandoutError as e: fail('MATH',ident,p+'.latex',b.get('latex'),str(e))
            elif kind in ('chem','quantity'):
                from handout_notation import notation_tex
                try:notation_tex(b)
                except HandoutError as e:fail('NOTATION',ident,p,b,str(e))
            elif kind=='image':
                fig=figures.get(b.get('figure_id')) if isinstance(b.get('figure_id'),str) else None
                if not fig or fig.get('decision')!='embed' or fig.get('unit_id')!=ident:
                    fail('FIGURE_REFERENCE',ident,p,b.get('figure_id'),'embed decision belonging to this unit')
            elif kind=='table':
                cols,rows=b.get('columns'),b.get('rows')
                if not isinstance(cols,list) or not cols or not isinstance(rows,list) or any(not isinstance(r,list) or len(r)!=len(cols) for r in rows):
                    fail('TABLE',ident,p,b,'rectangular rows matching columns')
                else:
                    for ri,row in enumerate([cols,*rows]):
                        for ci,cell in enumerate(row):
                            if isinstance(cell,dict):
                                try: validate_math(cell.get('math'))
                                except HandoutError as e: fail('MATH',ident,f'{p}.cells[{ri}][{ci}]',cell,str(e))
                            elif not isinstance(cell,str): fail('TABLE_CELL',ident,p,cell,'text or {math: latex}')
            elif kind in ('sequence','coin_recurrence','partition'):
                from handout_math import validate_claim
                try: validate_claim(b)
                except (HandoutError,ValueError,TypeError,KeyError,ZeroDivisionError) as e: fail('CLAIM',ident,p,b,str(e))
            else: fail('BLOCK_TYPE',ident,p+'.type',kind,'text/math/chem/quantity/image/table/sequence/coin_recurrence/partition')
    for i,u in enumerate(doc['units']):
        p=f'units[{i}]'
        if not isinstance(u,dict): fail('UNIT',None,p,u,'object');continue
        ident=u.get('id')
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',ident): fail('UNIT_ID',None,p+'.id',ident,'stable ASCII id');continue
        if ident in ids: fail('DUPLICATE',ident,p+'.id',ident,'unique unit id')
        ids.add(ident)
        if not isinstance(u.get('section_id'),str) or u.get('section_id') not in sections: fail('SECTION_REFERENCE',ident,p+'.section_id',u.get('section_id'),'existing section')
        for key in ('title','origin'):
            if not text(u.get(key)): fail('REQUIRED',ident,p+'.'+key,u.get(key),'non-empty text')
        if u.get('type') not in ('definition','theorem','example','note','exercise'): fail('UNIT_TYPE',ident,p+'.type',u.get('type'),'supported content type')
        if u.get('origin') not in ('course','ai_supplement','generated','comment','external'): fail('ORIGIN',ident,p+'.origin',u.get('origin'),'supported question/content origin')
        if u.get('answer_origin',u.get('origin')) not in ('course','ai_supplement','generated','external'): fail('ANSWER_ORIGIN',ident,p+'.answer_origin',u.get('answer_origin'),'separate valid answer origin')
        for key in ('conditions','pitfalls'):
            if not isinstance(u.get(key),list) or not all(isinstance(x,str) for x in u[key]): fail('TYPE',ident,p+'.'+key,u.get(key),'text array')
        for key in ('body','conclusion'): blocks(u.get(key),ident,p+'.'+key)
        steps=u.get('steps',[])
        if not isinstance(steps,list): fail('TYPE',ident,p+'.steps',steps,'array');steps=[]
        for j,step in enumerate(steps):
            if not isinstance(step,dict): fail('STEP',ident,f'{p}.steps[{j}]',step,'object');continue
            blocks(step.get('content'),ident,f'{p}.steps[{j}].content')
        if u.get('type') in ('example','exercise'):
            for key in ('body','conditions','motivation','steps','conclusion'):
                if not u.get(key): fail('INCOMPLETE_QUESTION',ident,p+'.'+key,u.get(key),'complete question, conditions, motivation and solution; do not invent missing material')
        refs=u.get('sources',[]); evidence=u.get('evidence',[])
        if not isinstance(refs,list): fail('TYPE',ident,p+'.sources',refs,'array');refs=[]
        if not isinstance(evidence,list): fail('TYPE',ident,p+'.evidence',evidence,'array');evidence=[]
        if u.get('origin')=='course' and not (refs and evidence): fail('COURSE_EVIDENCE',ident,p+'.evidence',evidence,'course time ranges and registered evidence')
        for j,ref in enumerate(refs):
            q=f'{p}.sources[{j}]'
            if not isinstance(ref,dict): fail('SOURCE',ident,q,ref,'source range object');continue
            if ref.get('video_id')!=source['video_id'] or ref.get('part')!=source['part']: fail('SOURCE_IDENTITY',ident,q,ref,'matching video and part')
            if not interval(ref.get('start'),ref.get('end'),duration): fail('TIME_RANGE',ident,q,ref,'0 <= start < end <= video duration')
        evidence_frames=set()
        for j,link in enumerate(evidence):
            q=f'{p}.evidence[{j}]'
            if not isinstance(link,dict): fail('EVIDENCE',ident,q,link,'typed evidence relation');continue
            kind,eid=link.get('kind'),link.get('id'); material=(fmap if kind=='frame' else smap if kind=='subtitle' else {}).get(eid) if isinstance(eid,str) else None
            if material is None: fail('EVIDENCE_MISSING',ident,q+'.id',eid,'existing evidence id','materials/frames.json' if kind=='frame' else 'materials/subtitles.json');continue
            if material.get('video_id',source['video_id'])!=source['video_id'] or material.get('part',source['part'])!=source['part']: fail('EVIDENCE_IDENTITY',ident,q,eid,'same video and part')
            valid_time=(number(material.get('time')) and 0<=material['time']<duration) if kind=='frame' else interval(material.get('start'),material.get('end'),duration)
            if not valid_time: fail('EVIDENCE_TIME',ident,q,eid,'valid original capture time',material.get('path'))
            if link.get('relation') not in RELATIONS or not text(link.get('reason')): fail('EVIDENCE_RELATION',ident,q,link,'explicit semantic relationship and reason')
            if kind=='frame':
                evidence_frames.add(eid)
                try:
                    if not within(root,material['path']).is_file(): fail('EVIDENCE_FILE',ident,q,eid,'existing frame file',material['path'])
                except HandoutError as e: fail('EVIDENCE_PATH',ident,q,material.get('path'),str(e))
        for fig in figures.values():
            if fig.get('unit_id')==ident and fig.get('frame_id') not in evidence_frames: fail('FIGURE_EVIDENCE',ident,p+'.evidence',fig.get('frame_id'),'figure registered in this unit evidence')
        review=u.get('review',{})
        if not isinstance(review,dict): review={}
        if review.get('status') not in ('verified','pending','insufficient'): fail('REVIEW',ident,p+'.review',review,'verified/pending/insufficient with reason')
        if not text(review.get('reason')): fail('REVIEW_REASON',ident,p+'.review.reason',None,'specific review reason')
        if review.get('status')!='verified': issues.append({'unit_id':ident,'reason':review.get('reason','未核对'),'impact':review.get('impact','content')})
        # A claimed check is valid only for the current content, and only with an actual artifact.
        check_records=u.get('checks',{})
        if not isinstance(check_records,dict):fail('CHECK_TYPE',ident,p+'.checks',check_records,'dimension -> record object');check_records={}
        current_digest=content_digest(u,doc.get('figures'))
        for dim,record in check_records.items():
            if not isinstance(record,dict):fail('CHECK_TYPE',ident,p+'.checks.'+dim,record,'artifact, sha256 and digest');continue
            try:
                artifact=within(root,record['artifact']); actual=read_json(artifact)
                if record.get('digest')!=current_digest or actual.get('target_digest')!=current_digest:
                    issues.append({'unit_id':ident,'dimension':dim,'reason':'内容已变更，旧核验失效','code':'CHECK_STALE'})
                elif actual.get('checker_version')!=file_hash(Path(__file__).with_name('handout_math.py')):
                    issues.append({'unit_id':ident,'dimension':dim,'reason':'核验程序版本已变更，须复核相应结果','code':'CHECKER_CHANGED'})
                elif record.get('sha256')!=file_hash(artifact) or actual.get('dimension')!=dim or actual.get('status')!='passed':
                    issues.append({'unit_id':ident,'dimension':dim,'reason':'核验产物不匹配或未通过','code':'CHECK_INVALID'})
                elif any(not within(root,e['path']).is_file() or file_hash(within(root,e['path']))!=e['sha256'] for e in actual.get('evidence_files',[])):
                    issues.append({'unit_id':ident,'dimension':dim,'reason':'复核使用的证据文件已变更','code':'CHECK_EVIDENCE_CHANGED'})
            except (HandoutError,KeyError,TypeError): issues.append({'unit_id':ident,'dimension':dim,'reason':'没有可核对的实际执行产物','code':'CHECK_EVIDENCE_MISSING'})
        if review.get('status')=='verified' and not check_records.get('fidelity'):
            issues.append({'unit_id':ident,'dimension':'fidelity','reason':'已核对声明缺少来源核对产物','code':'CHECK_EVIDENCE_MISSING'})
        if u.get('type') in ('example','exercise') and review.get('status')=='verified':
            for dim in ('calculation','proof'):
                if not check_records.get(dim): issues.append({'unit_id':ident,'dimension':dim,'reason':'该检查层尚未取得实际结果','code':'CHECK_NOT_RUN'})
    for fig in figures.values():
        if not isinstance(fig.get('unit_id'),str) or fig.get('unit_id') not in ids: fail('FIGURE_OWNER',None,'figures.unit_id',fig.get('unit_id'),'existing teaching unit')
        if fig.get('decision')=='omit_duplicate' and fig.get('covered_by'):
            replacements=fig['covered_by'] if isinstance(fig['covered_by'],list) else [fig['covered_by']]
            if any(not isinstance(r,str) or r not in set(fmap)|ids|set(figures) or r in (fig['id'],fig.get('frame_id')) for r in replacements):
                fail('FIGURE_REPLACEMENT',fig.get('unit_id'),'figures.covered_by',fig['covered_by'],'existing other frame, figure or teaching unit')
    for u in doc['units']:
        if not isinstance(u,dict):continue
        related=u.get('related_units',[])
        if not isinstance(related,list):fail('TYPE',u.get('id'),'related_units',related,'unit id array')
        elif any(not isinstance(r,str) or r not in ids for r in related):fail('RELATED_UNIT',u.get('id'),'related_units',related,'existing semantic unit ids')
    return {'valid':not errors,'errors':errors,'issues':issues,'release_ready':not errors and not issues,
            'layers':{'structure':not errors,'review_records_current':not issues},'notice':'结构、来源、计算、证明和视觉是独立检查层。'}


def minimal_unit(ident,section_id):
    return {'id':ident,'section_id':section_id,'type':'note','title':'待填写标题','origin':'course','answer_origin':'course',
            'conditions':[],'body':[],'motivation':'','steps':[],'conclusion':[],'pitfalls':[],
            'sources':[],'evidence':[],'related_units':[], 'review':{'status':'pending','reason':'内容尚待整理'},'checks':{}}


def scaffold(job):
    job=Path(job); source=read_json(job/'source.json')
    if (job/'handout.json').exists(): raise HandoutError('handout.json 已存在；使用 unit-put 或 migrate，不覆盖已有内容')
    doc={'schema_version':2,'title':source['title'],'level':source.get('level','待确认'),'prerequisites':[],
         'typography':{'math_font':'stix2'},
         'learning_goal':'','coverage':{'included':[],'omitted':[]},
         'sections':[{'id':'c1','title':'课程正文','start':0,'end':source['duration'],'origin':'model'}],
         'units':[],'figures':[]}
    write_json(job/'handout.json',doc);return {'path':'handout.json','protocol':2}


def query_index(job,start=0,end=None):
    job=Path(job); source=read_json(job/'source.json');end=source['duration'] if end is None else end
    if not interval(start,end,source['duration']): raise HandoutError('查询区间必须处于真实视频时长内')
    return {'video_id':source['video_id'],'part':source['part'],
            'subtitles':[s for s in read_json(job/'materials/subtitles.json') if s['start']<end and s['end']>start],
            'frames':[f for f in read_json(job/'materials/frames.json') if start<=f['time']<=end]}


def unit_put(job,path):
    job=Path(job);doc=read_json(job/'handout.json')
    from handout_workflow import guard_budget,failure
    guard_budget(job,'unit_put')
    if Path(path).suffix.lower() in ('.yaml','.yml'):
        import yaml
        try:unit=yaml.safe_load(Path(path).read_text(encoding='utf-8-sig'))
        except yaml.YAMLError as e:
            mark=getattr(e,'problem_mark',None)
            return {'saved':False,'errors':[diagnostic('UNIT_SYNTAX',None,f'{Path(path).name}:{mark.line+1 if mark else 0}',None,'safe YAML with literal blocks for LaTeX')]}
    else:unit=read_json(path)
    if not isinstance(unit,dict):return {'saved':False,'errors':[diagnostic('UNIT_TYPE',None,str(Path(path).name),unit,'unit object')]}
    candidate=copy.deepcopy(doc)
    matches=[i for i,u in enumerate(candidate['units']) if u.get('id')==unit.get('id')]
    if matches:candidate['units'][matches[0]]=unit
    else:candidate['units'].append(unit)
    report=validate_v2(candidate,read_json(job/'source.json'),read_json(job/'materials/subtitles.json'),read_json(job/'materials/frames.json'),job)
    local=[e for e in report['errors'] if e['unit_id'] in (None,unit.get('id'))]
    if local:
        failure(job,'unit_put',HandoutError(str(local[0])))
        return {'saved':False,'errors':local}
    write_json(job/'handout.json',candidate)
    write_json(job/'units'/(unit['id']+'.json'),unit)
    from handout_workflow import checkpoint
    checkpoint(job,'unit_'+unit['id'],['units/'+unit['id']+'.json'], 'check')
    state=read_json(job/'state.json');state.setdefault('repair_failures',{})['structure']=0;write_json(job/'state.json',state)
    return {'saved':True,'unit_id':unit['id'],'content_digest':content_digest(unit,doc.get('figures')),'issues':[x for x in report['issues'] if x.get('unit_id')==unit['id']]}


def unit_info(job,ident):
    job=Path(job);doc=read_json(job/'handout.json');unit=next((u for u in doc['units'] if u['id']==ident),None)
    if unit is None:raise HandoutError('单元不存在')
    paths={'materials/frames.json','materials/subtitles.json'}
    frames={f['id']:f for f in read_json(job/'materials/frames.json')}
    for e in unit.get('evidence',[]):
        if e.get('kind')=='frame' and e.get('id') in frames:paths.add(frames[e['id']]['path'])
    return {'unit':unit,'target_digest':content_digest(unit,doc.get('figures')),
            'evidence_files':[{'path':p,'sha256':file_hash(within(job,p))} for p in sorted(paths)]}


def migrate(job):
    job=Path(job);doc=read_json(job/'handout.json')
    if doc.get('schema_version')==2:return {'migrated':False,'reason':'already v2'}
    write_json(job/'handout.v1.backup.json',doc);doc['schema_version']=2;doc.setdefault('figures',[])
    for u in doc['units']:
        u['answer_origin']=u.get('answer_origin',u['origin']);u['checks']={};u['evidence']=[]
        for ref in u.get('sources',[]):
            for key,kind,rel in [('subtitle_ids','subtitle','audio'),('frame_ids','frame','same_board')]:
                for eid in ref.pop(key,[]):
                    if not any(e['id']==eid and e['kind']==kind for e in u['evidence']):
                        u['evidence'].append({'id':eid,'kind':kind,'relation':rel,'reason':'由v1来源迁移；须核对实际语义归属'})
        for group in [u.get('body',[]),u.get('conclusion',[]),*[s['content'] for s in u.get('steps',[])]]:
            for b in group:
                if b.get('type')=='image' and b.get('frame_id'):
                    fid='fig_'+u['id']+'_'+str(len(doc['figures'])+1)
                    doc['figures'].append({'id':fid,'unit_id':u['id'],'frame_id':b.pop('frame_id'),'decision':'embed',
                                          'reason':'v1原图暂保留；待按教学信息增量审查','crop':None})
                    b['figure_id']=fid
        u['review']={'status':'pending','reason':'协议迁移后重新核对来源和数学内容；旧声明不自动升级'}
    write_json(job/'handout.json',doc);return {'migrated':True,'backup':'handout.v1.backup.json','units':len(doc['units'])}
