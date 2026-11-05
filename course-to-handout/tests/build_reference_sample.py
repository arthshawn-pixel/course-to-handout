"""Materialize the reference regression job, preserving provenance and raw images."""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from handout_core import read_json,write_json,file_hash
from reference_course import course


def build(job,frames_dir,reference_pdf):
    job=Path(job).resolve();frames_dir=Path(frames_dir).resolve();reference_pdf=Path(reference_pdf).resolve()
    if (job/'handout.json').exists():raise RuntimeError('目标已有讲义；为保护人工修订，请选择新目录')
    (job/'materials/frames').mkdir(parents=True,exist_ok=True)
    source={'schema_version':2,'title':'【马尔科夫链】概率＋数列综合！高考热点！','level':'高中数学',
            'video_id':'BV1gAeX6DEpo_p1','part':1,'duration':1641.65,'url':'https://www.bilibili.com/video/BV1gAeX6DEpo/',
            'media_path':None,'fixture':False,'content_basis':'user_revision_pdf_v0.2','reference_pdf_sha256':file_hash(reference_pdf)}
    write_json(job/'source.json',source);write_json(job/'state.json',{'version':'0.2.0','stages':{},'access':{'status':'ready','reason':'复用已采集原帧及用户修订稿；未重新转写'}})
    ids=[60,300,650,1020,1380,1600,1620];frames=[]
    for t in ids:
        ident='f'+str(t*1000).zfill(9);p=frames_dir/(ident+'.png');dest=job/'materials/frames'/p.name;shutil.copyfile(p,dest)
        frames.append({'id':ident,'time':t,'path':dest.relative_to(job).as_posix(),'video_id':source['video_id'],'part':1,'origin':'preserved_original_ffmpeg_frame'})
    shutil.copyfile(reference_pdf,job/'materials/reference-revised.pdf')
    write_json(job/'materials/frames.json',frames);write_json(job/'materials/subtitles.json',[])
    doc=course(source)
    for u in doc['units']:
        for s in u.get('steps',[]):s['origin']=u.get('answer_origin',u['origin'])
    # Preserve every sampled raw frame; only one teaching-value crop is embedded.
    for frame in frames:
        if frame['id']=='f000300000':continue
        owners=[u for u in doc['units'] if any(e['id']==frame['id'] for e in u.get('evidence',[]))]
        if owners:
            doc['figures'].append({'id':'evidence-'+frame['id'],'unit_id':owners[0]['id'],'frame_id':frame['id'],
                                  'decision':'evidence_only','reason':'原题与推导已完整重排，保留原帧核对；不将重复题干与背景嵌入学生版','crop':None})
    write_json(job/'handout.json',doc)
    for u in doc['units']:write_json(job/'units'/(u['id']+'.json'),u)
    return {'job':str(job),'units':len(doc['units']),'original_examples':4,'exercises':4,'raw_frames':len(frames),'embedded':1}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('job');p.add_argument('--frames',required=True);p.add_argument('--reference-pdf',required=True);a=p.parse_args()
    print(build(a.job,a.frames,a.reference_pdf))
