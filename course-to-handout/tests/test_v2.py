import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from handout_core import HandoutError,write_json,read_json,stage,file_hash
from handout_v2 import minimal_unit,validate_v2,content_digest,query_index
from handout_math import partition_check,verify_unit,enumerate_paths
from handout_workflow import resume
from handout_student import merged_ranges
from handout_text import text_tex


class V2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.job=Path(self.tmp.name)
        (self.job/'materials').mkdir();(self.job/'materials/frame.png').write_bytes(b'fixture-image')
        self.source={'video_id':'BVtest','part':1,'duration':1500,'title':'数学课','url':''}
        self.subs=[{'id':'sub-A','start':1190,'end':1200,'text':'例题结论','video_id':'BVtest','part':1},
                   {'id':'sub-B','start':1200,'end':1210,'text':'总结','video_id':'BVtest','part':1}]
        self.frames=[{'id':'frame-2300','time':1380,'path':'materials/frame.png','video_id':'BVtest','part':1}]
        u=minimal_unit('example3','c1');u.update(title='投篮例题',origin='course',body=[{'type':'text','text':'给定当前状态，讨论下一步。'}],
              sources=[{'video_id':'BVtest','part':1,'start':1180,'end':1220}],
              evidence=[{'kind':'frame','id':'frame-2300','relation':'residual','reason':'23:00画面仍是本题板书，口述已转入总结'},
                        {'kind':'subtitle','id':'sub-A','relation':'audio','reason':'结论位于前一包'},
                        {'kind':'subtitle','id':'sub-B','relation':'audio','reason':'总结跨入下一包'}])
        self.doc={'schema_version':2,'title':'数学课','level':'高中','prerequisites':[],
             'sections':[{'id':'c1','title':'例题','start':1100,'end':1230}], 'units':[u],'figures':[]}
        for p,v in [('source.json',self.source),('state.json',{'stages':{}}),('materials/subtitles.json',self.subs),('materials/frames.json',self.frames),('handout.json',self.doc)]:write_json(self.job/p,v)
    def check(self):return validate_v2(self.doc,self.source,self.subs,self.frames,self.job)
    def test_real_capture_time_and_residual_board_relation_are_independent(self):
        self.assertTrue(self.check()['valid'],self.check());self.assertEqual(self.frames[0]['time'],1380)
    def test_question_can_span_evidence_packets_without_changing_audio_time(self):
        self.assertTrue(self.check()['valid']);self.assertEqual(len(query_index(self.job,1180,1220)['subtitles']),2)
    def test_missing_reference_has_unit_path_value_and_expected_location(self):
        self.doc['units'][0]['evidence'][0]['id']='missing'
        error=self.check()['errors'][0]
        self.assertEqual(error['code'],'EVIDENCE_MISSING');self.assertEqual(error['unit_id'],'example3');self.assertIn('evidence[0]',error['path']);self.assertEqual(error['value'],'missing');self.assertTrue(error['expected']);self.assertTrue(error['evidence'])
    def test_illegal_source_times_are_not_repaired_by_expanding_chapter(self):
        self.doc['units'][0]['sources'][0].update(start=1400,end=1300)
        self.assertIn('TIME_RANGE',[e['code'] for e in self.check()['errors']])
    def test_wrong_video_frame_is_rejected_even_if_time_is_valid(self):
        self.frames[0]['video_id']='another';self.assertFalse(self.check()['valid'])
    def test_same_frame_with_small_symbol_change_is_not_automatically_removed(self):
        from PIL import Image,ImageDraw
        from handout_figures import candidates
        a=Image.new('RGB',(200,100),'white');ImageDraw.Draw(a).text((80,30),'x > 0',fill='black');a.save(self.job/'materials/a.png')
        b=a.copy();ImageDraw.Draw(b).line((80,43,100,43),fill='black');b.save(self.job/'materials/b.png')
        write_json(self.job/'materials/frames.json',[{'id':'a','time':1,'path':'materials/a.png'},{'id':'b','time':2,'path':'materials/b.png'}])
        result=candidates(self.job);self.assertEqual(result['auto_deleted'],0);self.assertEqual(result['neighbor_pairs'][0]['decision'],'review_information_increment')
    def test_dropped_unique_intermediate_frame_requires_a_covering_evidence(self):
        self.doc['figures']=[{'id':'f','unit_id':'example3','frame_id':'frame-2300','decision':'omit_duplicate','reason':'稍后擦除'}]
        self.assertIn('FIGURE_REPLACEMENT',[e['code'] for e in self.check()['errors']])
    def test_old_coin_suffix_partition_is_rejected_while_correct_prefix_and_suffix_pass(self):
        bad=partition_check('suffix',['T','HT','HHT'])
        self.assertFalse(bad['passed']);self.assertTrue(bad['counterexamples'])
        self.assertTrue(partition_check('prefix',['T','HT','HHT'])['passed']);self.assertTrue(partition_check('suffix',['T','TH','THH'])['passed'])
    def test_numeric_coin_success_cannot_mask_invalid_proof(self):
        u=self.doc['units'][0];u['conclusion']=[{'type':'coin_recurrence','coefficients':['1/2','1/4','1/8']},
              {'type':'partition','direction':'suffix','patterns':['T','HT','HHT']}]
        write_json(self.job/'handout.json',self.doc)
        self.assertEqual(verify_unit(self.job,'example3','calculation')['status'],'passed')
        self.assertEqual(verify_unit(self.job,'example3','proof')['status'],'failed')
    def test_changing_proof_text_invalidates_the_old_actual_check(self):
        u=self.doc['units'][0];u['conclusion']=[{'type':'partition','direction':'prefix','patterns':['T','HT','HHT']}]
        write_json(self.job/'handout.json',self.doc);verify_unit(self.job,'example3','proof')
        self.doc=read_json(self.job/'handout.json');self.doc['units'][0]['steps']=[{'content':[{'type':'text','text':'新增分类解释'}]}]
        self.assertIn('CHECK_STALE',[x.get('code') for x in self.check()['issues']])
    def test_no_execution_artifact_cannot_be_called_program_verification(self):
        u=self.doc['units'][0];u['checks']={'calculation':{'artifact':'checks/invented.json','sha256':'none','digest':content_digest(u)}}
        self.assertIn('CHECK_EVIDENCE_MISSING',[x.get('code') for x in self.check()['issues']])
    def test_semantic_digest_excludes_only_render_style_not_conditions(self):
        u=self.doc['units'][0];before=content_digest(u);u['display']={'accent':'slate'};self.assertEqual(before,content_digest(u));u['conditions']=['n≥2'];self.assertNotEqual(before,content_digest(u))
    def test_source_ranges_merge_only_adjacent_parts_of_the_same_unit(self):
        u={'sources':[{'video_id':'v','part':1,'start':1,'end':5},{'video_id':'v','part':1,'start':6,'end':9},{'video_id':'v','part':1,'start':100,'end':110}]}
        result=merged_ranges(u);self.assertEqual([(r['start'],r['end']) for r in result],[(1,9),(100,110)])
    def test_media_retry_budget_is_bounded_and_records_the_failure(self):
        def fail():raise HandoutError('fixed deterministic failure')
        for _ in range(2):
            with self.assertRaises(HandoutError):stage(self.job,'fetch',{},fail)
        with self.assertRaisesRegex(HandoutError,'BUDGET_EXHAUSTED'):stage(self.job,'fetch',{},fail)
        self.assertTrue((self.job/'diagnostics/fetch.json').exists())
    def test_resume_uses_file_hashes_not_a_previous_model_summary(self):
        out=self.job/'answer.json'
        stage(self.job,'answer',{},lambda:(write_json(out,{'value':1}) or [out]))
        self.assertIn('answer',resume(self.job)['valid_checkpoints']);out.write_text('changed',encoding='utf-8')
        self.assertIn('answer',resume(self.job)['stale_checkpoints'])
    def test_text_math_and_exam_roman_numerals_have_separate_normalization(self):
        out=text_tex('新高考Ⅰ卷 x₀² ≤ 1，𝑛')
        self.assertIn('新高考I卷',out);self.assertIn(r'\leq',out);self.assertIn(r'{}_0',out);self.assertIn(r'\ensuremath{𝑛}',out)
    def test_six_physical_probability_models_match_the_written_closed_claims(self):
        from fractions import Fraction as F
        models=[
          ([['1/4','3/4'],['1/2','1/2']],['2/3','1/3'],['2/5','4/15','-1/4']),
          ([[str(F(int(i!=j),3)) for j in range(4)] for i in range(4)],['0','1/3','1/3','1/3'],['1/4','-1/4','-1/3']),
          ([['3/5','2/5'],['1/5','4/5']],['1/2','1/2'],['1/3','1/6','2/5']),
          ([['2/3','1/3'],['1/3','2/3']],['2/3','1/3'],['1/2','1/6','1/3']),
          ([[str(F(int(i!=j),2)) for j in range(3)] for i in range(3)],['0','1/2','1/2'],['1/3','-1/3','-1/2']),
          ([['2/3','1/3'],['1/2','1/2']],['1/2','1/2'],['3/5','-1/10','1/6'])]
        for matrix,initial,(constant,coefficient,base) in models:
            for n in range(1,11):
                self.assertEqual(enumerate_paths(matrix,initial,[0],n),F(constant)+F(coefficient)*F(base)**(n-1))
    def test_independent_state_sequence_is_a_markov_counterexample_to_required_dependence(self):
        from fractions import Fraction as F
        matrix=[['1/3','2/3'],['1/3','2/3']]
        for n in range(1,8):self.assertEqual(enumerate_paths(matrix,['1/3','2/3'],[0],n),F(1,3))
        self.assertEqual(matrix[0],matrix[1])
    def test_unit_yaml_literal_math_is_serialized_without_rewriting_backslashes(self):
        from handout_v2 import unit_put
        path=self.job/'new-unit.yaml'
        path.write_text('id: note2\nsection_id: c1\ntitle: 公式\ntype: note\norigin: generated\nconditions: []\npitfalls: []\nbody:\n  - type: math\n    latex: |\n      x=\\frac{1}{2}\nconclusion: []\nsources: []\nevidence: []\nreview:\n  status: pending\n  reason: 新内容待核对\n',encoding='utf-8')
        result=unit_put(self.job,path);self.assertTrue(result['saved'],result)
        actual=read_json(self.job/'handout.json')['units'][-1]['body'][0]['latex'];self.assertEqual(actual.strip(),r'x=\frac{1}{2}')
    def test_editing_an_existing_unit_preserves_teaching_order(self):
        from handout_v2 import unit_put
        second=copy.deepcopy(self.doc['units'][0]);second['id']='second';self.doc['units'].append(second)
        write_json(self.job/'handout.json',self.doc)
        first=copy.deepcopy(self.doc['units'][0]);first['title']='已修订'
        write_json(self.job/'edit.json',first);self.assertTrue(unit_put(self.job,self.job/'edit.json')['saved'])
        self.assertEqual([u['id'] for u in read_json(self.job/'handout.json')['units']],['example3','second'])
    def test_crop_change_invalidates_a_previous_math_record(self):
        u=self.doc['units'][0];u['conclusion']=[{'type':'partition','direction':'prefix','patterns':['T','HT','HHT']}]
        self.doc['figures']=[{'id':'fig','unit_id':'example3','frame_id':'frame-2300','decision':'evidence_only','reason':'核对符号','crop':[0,0,10,10]}]
        write_json(self.job/'handout.json',self.doc);verify_unit(self.job,'example3','proof')
        self.doc=read_json(self.job/'handout.json');self.doc['figures'][0]['crop'][2]=11
        self.assertIn('CHECK_STALE',[x.get('code') for x in self.check()['issues']])
    def test_structure_repair_stops_at_configured_budget(self):
        from handout_v2 import unit_put
        write_json(self.job/'config.json',{'repair_budgets':{'structure':1}})
        write_json(self.job/'broken.json',{'id':'bad'})
        self.assertFalse(unit_put(self.job,self.job/'broken.json')['saved'])
        with self.assertRaisesRegex(HandoutError,'BUDGET_EXHAUSTED'):unit_put(self.job,self.job/'broken.json')


if __name__=='__main__':unittest.main()
