"""Optional real compiler acceptance; use a NEW job and configured runtime."""
import argparse,copy,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from handout_core import write_json,read_json,file_hash
from handout_v2 import content_digest
from handout_student import render_student
from handout_workflow import preflight
import handout_render

def main(job):
    job=Path(job).resolve()
    if job.exists():raise ValueError('Use a new acceptance directory')
    (job/'materials').mkdir(parents=True)
    source={'title':'另一课程：代数递推','level':'高中','duration':2,'video_id':'algebra-fixture','part':1,'url':'','fixture':True}
    u={'id':'algebra','section_id':'c1','title':'自制代数递推','type':'example','origin':'generated','answer_origin':'generated',
       'conditions':['n为正整数'],'body':[{'type':'text','text':'a₁=1，aₙ₊₁=2aₙ+1，求通项。'}],
       'motivation':'平移后成为等比数列。','steps':[{'content':[{'type':'math','latex':r'a_{n+1}+1=2(a_n+1).'}]}],
       'conclusion':[{'type':'math','latex':r'a_n=2^n-1.'}],'pitfalls':[],'sources':[],'evidence':[],
       'review':{'status':'pending','reason':'自制排版回归，未做来源复核'},'checks':{}}
    doc={'schema_version':2,'title':source['title'],'level':'高中','prerequisites':['等比数列'],
         'sections':[{'id':'c1','title':'递推','start':0,'end':2}],'units':[u],'figures':[]}
    for name,value in [('source.json',source),('state.json',{'stages':{}}),('materials/frames.json',[]),('materials/subtitles.json',[]),('handout.json',doc)]:write_json(job/name,value)
    paths=['source.json','materials/frames.json','materials/subtitles.json']
    upstream={p:file_hash(job/p) for p in paths}
    result={};key=lambda:read_json(job/'state.json')['stages']['render_v2_reading_draft']['key']
    first=render_student(job,draft=True,engine='tectonic');k1=key()
    second=render_student(job,draft=True,engine='tectonic');assert second['cached']
    doc['units'][0]['body'][0]['text']+=' 请说明初值。';write_json(job/'handout.json',doc)
    third=render_student(job,draft=True,engine='tectonic');assert not third['cached'] and key()!=k1
    semantic=content_digest(doc['units'][0]);style=render_student(job,draft=True,engine='tectonic',accent='slate',margin=21)
    assert not style['cached'] and semantic==content_digest(read_json(job/'handout.json')['units'][0])
    assert upstream=={p:file_hash(job/p) for p in paths}
    original=handout_render.ROOT;shadow=job/'skill-fingerprint-fixture';shutil.copytree(original,shadow,ignore=shutil.ignore_patterns('__pycache__','tests','tools'))
    try:
        handout_render.ROOT=shadow
        (shadow/'scripts/handout_text.py').write_text((shadow/'scripts/handout_text.py').read_text(encoding='utf-8')+'\n# fingerprint regression\n',encoding='utf-8')
        previous=key();changed=render_student(job,draft=True,engine='tectonic',accent='slate',margin=21)
        assert not changed['cached'] and previous!=key()
    finally:handout_render.ROOT=original
    result={'new_course':'algebra fixture, no Markov-specific input','cache_reuse':second['cached'],'one_character_edit_invalidates_render':not third['cached'],
      'style_only_keeps_math_digest':True,'style_only_keeps_upstream_hashes':True,'wrapper_normalizer_change_invalidates_cache':not changed['cached'],
      'layout_audit':read_json(job/'build/student-reading/layout-report.json')}
    assert not result['layout_audit']['warnings']
    write_json(job/'render-acceptance.json',result);print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('job');main(p.parse_args().job)
