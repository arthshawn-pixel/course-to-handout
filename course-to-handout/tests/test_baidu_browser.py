import json,shutil,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from handout_core import HandoutError,read_json,write_json,source_link
import handout_baidu as b

class BrowserBaiduTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from handout_media import run_media
        cls.media_tmp=tempfile.TemporaryDirectory();cls.media=Path(cls.media_tmp.name)/'clip.mp4'
        run_media(['-y','-f','lavfi','-i','color=c=blue:s=160x120:r=2','-f','lavfi','-i','anullsrc=r=16000:cl=mono','-t','2','-c:v','libx264','-c:a','aac',str(cls.media)])
        cls.size=cls.media.stat().st_size
    @classmethod
    def tearDownClass(cls):cls.media_tmp.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.job=self.root/'job';self.url='https://pan.baidu.com/s/1abcdefG'
        b.initialize(self.job,self.url+'?pwd=ag42',intent='video_only')
    def send(self,event,**kwargs):
        value={'event':event,'observed_url':self.url,'evidence':{'kind':'browser_snapshot','tool':'test-browser-fixture','reference':'fixture-observation'},**kwargs}
        path=self.job/'observation.json';write_json(path,value);return b.observe(self.job,path)
    def files(self,items=None):
        return self.send('files_visible',files=items if items is not None else [{'id':'video1','name':'clip.mp4','bytes':self.size,'is_dir':False}])
    def start(self):self.files();return self.send('download_started',method='official_client')
    def incoming(self):return Path(b.plan(self.job)['download_directory'])
    def make_ready(self):
        self.start();p=self.incoming()/'clip.mp4';shutil.copyfile(self.media,p);return p
    def mature(self):
        task=read_json(self.job/b.TASK);task['candidate']['first_seen']-=10;write_json(self.job/b.TASK,task)
    def test_full_pasted_share_nbsp_and_code_conflict(self):
        self.assertEqual(b.parse_share('链接:'+self.url+'\u00a0\n提取码:ag42')['code'],'ag42')
        with self.assertRaisesRegex(HandoutError,'CONFLICT'):b.parse_share(self.url+'?pwd=ag42 提取码:xy99')
    def test_malicious_domains_ports_and_multiple_links_rejected(self):
        for text in ('https://pan.baidu.com.evil.test/s/1abcdefG','https://x:y@pan.baidu.com/s/1abcdefG','https://pan.baidu.com:999/s/1abcdefG',self.url+' https://pan.baidu.com/s/1zyxwvut'):
            with self.assertRaises(HandoutError):b.parse_share(text)
    def test_extraction_code_is_not_in_public_status_or_source(self):
        self.assertNotIn('ag42',json.dumps(b.status_report(self.job)))
        self.assertNotIn('ag42',json.dumps(read_json(self.job/'source.json')))
        self.assertEqual(b.plan(self.job)['browser']['extraction_code'],'ag42')
    def test_single_video_selects_and_has_job_local_destination(self):
        result=self.files();self.assertEqual(result['status'],'ready_to_download')
        self.assertTrue(self.incoming().resolve().is_relative_to(self.job.resolve()))
        self.assertEqual(read_json(self.job/'source.json')['file_id'],'video1')
    def test_login_is_waiting_and_user_message_cannot_claim_file_visibility(self):
        result=self.send('waiting_login',observed_url='https://passport.baidu.com/login?ticket=PRIVATE')
        self.assertEqual(result['status'],'waiting_login')
        self.assertNotIn('PRIVATE',(self.job/b.TASK).read_text(encoding='utf-8'))
        with self.assertRaises(HandoutError):self.send('files_visible',files=[],evidence={'kind':'user_message','tool':'chat','reference':'user-said-done'})
    def test_wrong_share_or_unverifiable_url_does_not_advance(self):
        for url in ('https://evil.test/s/1abcdefG','https://pan.baidu.com/s/1zyxwvut','https://pan.baidu.com/disk/main','https://pan.baidu.com:8443/s/1abcdefG'):
            with self.assertRaises(HandoutError):self.send('files_visible',files=[],observed_url=url)
        self.assertEqual(b.status_report(self.job)['status'],'awaiting_browser')
    def test_cookie_and_signed_url_fields_are_not_persisted(self):
        with self.assertRaises(HandoutError):self.send('files_visible',files=[],cookies='DO_NOT_STORE')
        with self.assertRaises(HandoutError):self.files([{'id':'x','name':'x.mp4','bytes':1,'dlink':'DO_NOT_STORE'}])
        self.assertNotIn('DO_NOT_STORE',(self.job/b.TASK).read_text(encoding='utf-8'))
    def test_multiple_videos_require_explicit_selection(self):
        result=self.files([{'id':'a','name':'a.mp4','bytes':1},{'id':'b','name':'b.mp4','bytes':2},{'id':'c','name':'folder','is_dir':True}])
        self.assertEqual(result['status'],'waiting_selection')
        with self.assertRaises(HandoutError):b.select(self.job,'c')
        self.assertEqual(b.select(self.job,'b')['selected']['id'],'b')
    def test_path_traversal_and_approximate_sizes_rejected(self):
        for item in ({'name':'../clip.mp4'},{'name':'clip.mp4','bytes':'29.6MB'},{'id':'../../x','name':'clip.mp4'}):
            with self.assertRaises(HandoutError):self.files([item])
    def test_download_cannot_start_before_selection_or_be_called_complete(self):
        with self.assertRaises(HandoutError):self.send('download_started',method='official_client')
        with self.assertRaises(HandoutError):self.send('acquired')
    def test_tool_stop_preserves_resume_action_and_never_claims_download(self):
        result=self.send('tool_unavailable',reason='cannot_verify_url')
        self.assertEqual(result['status'],'tool_unavailable');self.assertIsNone(read_json(self.job/'source.json')['media_path'])
        from handout_workflow import resume
        self.assertEqual(resume(self.job)['acquisition']['status'],'tool_unavailable')
    def test_fetch_returns_browser_plan_without_calling_anonymous_extractor(self):
        from lecture import fetch
        with patch('handout_media.acquire_bilibili',side_effect=AssertionError('must not call')):
            result=fetch(SimpleNamespace(job=str(self.job)))
        self.assertEqual(result['browser']['login'],'user_only')
    def test_watch_before_download_started_does_not_adopt_file(self):
        self.files();shutil.copyfile(self.media,self.incoming()/'clip.mp4')
        self.assertEqual(b.watch(self.job)['status'],'ready_to_download')
    def test_partial_download_does_not_become_acquired(self):
        self.make_ready();(self.incoming()/'clip.mp4.crdownload').write_bytes(b'partial')
        result=b.watch(self.job);self.assertEqual(result['status'],'downloading')
        self.assertEqual(result['download_progress']['reason'],'partial_download_present')
        self.assertIsNone(read_json(self.job/'source.json')['media_path'])
    def test_stable_completed_video_is_decoded_and_reused(self):
        self.make_ready();self.assertEqual(b.watch(self.job)['status'],'checking_download');self.mature()
        result=b.watch(self.job);self.assertEqual(result['status'],'acquired');self.assertTrue(result['receipt']['first_frame_decoded'])
        self.assertTrue(result['receipt']['has_audio']);self.assertTrue(b.watch(self.job)['media_current'])
        self.assertEqual(result['download_progress']['reason'],'local_video_validated')
        self.assertIn('停止',result['next_action']);self.assertFalse((self.job/'handout.json').exists())
    def test_size_mismatch_stays_pending_and_has_specific_diagnostic(self):
        p=self.make_ready();p.write_bytes(b'short')
        self.assertEqual(b.watch(self.job)['download_progress']['reason'],'size_mismatch')
        with self.assertRaisesRegex(HandoutError,'SIZE_MISMATCH'):b.attach(self.job,p)
        self.assertTrue((self.job/'diagnostics/baidu_import.json').exists())
    def test_fake_mp4_is_rejected_even_when_size_and_name_match(self):
        self.start();p=self.incoming()/'clip.mp4';p.write_bytes(b'x'*self.size)
        with self.assertRaises(HandoutError):b.attach(self.job,p)
        self.assertEqual(b.status_report(self.job)['status'],'validation_failed')
        self.assertIsNone(read_json(self.job/'source.json')['media_path'])
    def test_old_file_present_before_click_is_not_silently_reused(self):
        self.files();p=self.incoming()/'clip.mp4';shutil.copyfile(self.media,p)
        self.files();self.send('download_started',method='browser_download')
        self.assertEqual(b.watch(self.job)['download_progress']['reason'],'file_not_found')
    def test_duplicate_candidates_do_not_choose_arbitrarily(self):
        self.make_ready();(self.incoming()/'sub').mkdir();shutil.copyfile(self.media,self.incoming()/'sub/clip.mp4')
        self.assertEqual(b.watch(self.job)['download_progress']['reason'],'multiple_candidates')
    def test_media_modification_invalidates_completed_state(self):
        p=self.make_ready();b.attach(self.job,p);p.write_bytes(p.read_bytes()+b'changed')
        self.assertEqual(b.status_report(self.job)['status'],'validation_stale')
    def test_receipt_modification_invalidates_completed_state(self):
        p=self.make_ready();b.attach(self.job,p)
        write_json(self.job/'acquisition/baidu-receipt.json',{'made_up':True})
        self.assertEqual(b.status_report(self.job)['status'],'validation_stale')
    def test_explicit_import_needs_source_confirmation_without_browser_selection(self):
        with self.assertRaisesRegex(HandoutError,'SOURCE_CONFIRMATION'):b.attach(self.job,self.media)
        result=b.attach(self.job,self.media,source_confirmed=True)
        self.assertEqual(result['receipt']['source_assurance'],'user_confirmed_local_file')
        self.assertTrue((self.job/result['receipt']['media_path']).is_file())
    def test_renamed_file_needs_confirmation(self):
        self.files();p=self.root/'renamed.mp4';shutil.copyfile(self.media,p)
        with self.assertRaisesRegex(HandoutError,'FILENAME_MISMATCH'):b.attach(self.job,p)
        self.assertEqual(b.attach(self.job,p,True)['receipt']['source_assurance'],'host_confirmed_download_with_rename')
    def test_pause_requires_explicit_user_resume(self):
        self.start();self.send('paused',reason='user_paused')
        self.assertEqual(b.watch(self.job)['status'],'paused')
        with self.assertRaises(HandoutError):self.files()
        self.send('resumed',evidence={'kind':'user_message','tool':'chat','reference':'explicit-continue'})
        self.assertEqual(b.status_report(self.job)['status'],'downloading')
    def test_watch_limits_prevent_indefinite_blocking(self):
        for timeout,stable in ((-1,3),(61,3),(0,0)):
            with self.assertRaises(HandoutError):b.watch(self.job,timeout,stable)
    def test_source_repair_budget_stops_repeating_failed_imports(self):
        self.start();p=self.incoming()/'clip.mp4';p.write_bytes(b'bad')
        write_json(self.job/'config.json',{'repair_budgets':{'source':1}})
        with self.assertRaises(HandoutError):b.attach(self.job,p)
        with self.assertRaisesRegex(HandoutError,'BUDGET_EXHAUSTED'):b.attach(self.job,p)
    def test_share_source_url_does_not_fabricate_time_navigation(self):
        source=read_json(self.job/'source.json')
        self.assertEqual(source_link(source,125),self.url)
    def test_unknown_size_needs_official_completion_observation(self):
        self.files([{'id':'video1','name':'clip.mp4','bytes':None}]);self.send('download_started',method='browser_download')
        p=self.incoming()/'clip.mp4';shutil.copyfile(self.media,p)
        self.assertEqual(b.watch(self.job)['download_progress']['reason'],'awaiting_completion_confirmation')
        self.send('download_completed');b.watch(self.job);self.mature()
        result=b.watch(self.job);self.assertEqual(result['status'],'acquired')
        self.assertEqual(result['receipt']['completion_basis'],'host_observed_completion')
    def test_unknown_size_import_needs_completion_or_user_confirmation(self):
        self.files([{'id':'video1','name':'clip.mp4'}])
        with self.assertRaisesRegex(HandoutError,'COMPLETION_CONFIRMATION'):b.attach(self.job,self.media)
        self.assertEqual(b.attach(self.job,self.media,True)['receipt']['completion_basis'],'user_confirmed_file')
    def test_user_message_cannot_claim_official_completion(self):
        self.start()
        with self.assertRaises(HandoutError):self.send('download_completed',evidence={'kind':'user_message','tool':'chat','reference':'said-done'})
    def test_add_video_uses_baidu_validation_and_receipt(self):
        from lecture import add_video
        self.files()
        result=add_video(SimpleNamespace(job=str(self.job),file=str(self.media)))
        self.assertEqual(result['status'],'acquired');self.assertTrue((self.job/'acquisition/baidu-receipt.json').exists())
    def test_student_source_labels_distinguish_netdisk_from_bilibili(self):
        from handout_student import segment_label
        self.assertEqual(segment_label({'provider':'baidu'},1),'网盘视频')
        self.assertEqual(segment_label({},2),'P2')

if __name__=='__main__':unittest.main()
