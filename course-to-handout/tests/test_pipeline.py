"""Behavioral invariants: sources, math injection, review gates, cache recovery."""
import argparse
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from handout_core import HandoutError, parse_subtitles, validate_math, validate_document, write_json, stage, within, source_link
from lecture import initialize, import_subtitles, import_browser_subtitles, prepare, access
from handout_browser import subtitle_status, validate_browser_export, record_subtitle_probe
from handout_render import render, escape
from make_demo import make_content, TRANSCRIPT


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.job = self.root / "job"
        self.args = argparse.Namespace(job=str(self.job), video=None, url=None, duration=600,
                    title="测试课程", level="高中", part=2, fixture=True, video_id=None)
        initialize(self.args)
        self.source = json.loads((self.job / "source.json").read_text(encoding="utf-8"))
        self.subs = [{"id": f"s{i:05}", "start": a, "end": b, "text": s} for i,(a,b,s) in enumerate(TRANSCRIPT, 1)]
        self.frames = [{"id": f"f{t * 1000:09}", "time": t, "path": "materials/frame.png"} for t in (60,150,240,330,390,540)]
        (self.job / "materials/frame.png").write_bytes(b"test")
        self.doc = make_content(self.source, {f["time"]: f["id"] for f in self.frames})
    def check(self, doc=None):
        return validate_document(doc or self.doc, self.source, self.subs, self.frames, self.job)
    def test_valid_document_remains_pending(self):
        report = self.check()
        self.assertTrue(report["valid"], report)
        self.assertFalse(report["release_ready"])
        self.assertEqual(len(report["issues"]), 6)
    def test_out_of_range_part_and_invented_evidence(self):
        for key, value in [("end", 999), ("part", 1), ("subtitle_ids", ["s99999"]), ("frame_ids", ["not-a-frame"])]:
            with self.subTest(key=key):
                doc = copy.deepcopy(self.doc); doc["units"][0]["sources"][0][key] = value
                self.assertFalse(self.check(doc)["valid"])
    def test_evidence_must_overlap_not_just_exist(self):
        doc = copy.deepcopy(self.doc)
        doc["units"][0]["sources"][0]["subtitle_ids"] = ["s00012"]
        self.assertFalse(self.check(doc)["valid"])
    def test_unrelated_board_is_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["units"][1]["body"].append({"type":"image", "frame_id":self.frames[-1]["id"]})
        self.assertFalse(self.check(doc)["valid"])
    def test_verified_requires_actual_review_record(self):
        self.doc["units"][0]["review"] = {"status":"verified", "reason":"looks good"}
        self.assertFalse(self.check()["valid"])
    def test_generated_questions_require_related_material(self):
        self.doc["units"][-1]["related_units"] = ["missing"]
        self.assertFalse(self.check()["valid"])
    def test_missing_steps_or_method_is_not_complete_example(self):
        self.doc["units"][1]["steps"] = []
        self.assertFalse(self.check()["valid"])
    def test_math_input_cannot_execute_tex(self):
        for formula in [r"\input{secret}", r"\write18{anything}", r"\csname input\endcsname", r"\end{document}", "^^5cinput{foo}", "x%ignored", "$x$"]:
            with self.subTest(formula=formula), self.assertRaises(HandoutError): validate_math(formula)
        validate_math(r"\begin{pmatrix}1&2\\3&4\end{pmatrix}")
        validate_math(r"\frac{x-1}{x}\ge0")
    def test_paths_stay_in_job(self):
        with self.assertRaises(HandoutError): within(self.job, "../outside.png")
    def test_pending_document_cannot_publish(self):
        write_json(self.job / "handout.json", self.doc)
        write_json(self.job / "materials/subtitles.json", self.subs)
        write_json(self.job / "materials/frames.json", self.frames)
        with self.assertRaisesRegex(HandoutError, "草稿"): render(self.job, draft=False)
    def test_cache_detects_corruption_and_failed_stage_can_resume(self):
        output = self.job / "result.json"
        calls = []
        def produce(): calls.append(1); write_json(output, {"ok":True}); return [output]
        self.assertFalse(stage(self.job,"test", {"input":1}, produce)["cached"])
        self.assertTrue(stage(self.job,"test", {"input":1}, produce)["cached"])
        output.write_text("corrupted", encoding="utf-8")
        self.assertFalse(stage(self.job,"test", {"input":1}, produce)["cached"])
        self.assertEqual(len(calls), 2)
        def fail(): raise HandoutError("expected failure")
        with self.assertRaises(HandoutError): stage(self.job,"other", {}, fail)
        self.assertFalse(stage(self.job,"other", {}, produce)["cached"])
    def test_browser_ready_needs_actual_resource_check(self):
        args = argparse.Namespace(job=str(self.job), state="ready", resource_verified=False)
        with self.assertRaises(HandoutError): access(args)
        args.resource_verified = True
        self.assertEqual(access(args)["status"], "ready")
        args.state = "paused"
        self.assertEqual(access(args)["status"], "paused")
    def test_subtitles_preserve_time_and_detect_wrong_part(self):
        path = self.root / "input.srt"
        path.write_text("1\n00:00:01,000 --> 00:00:05,200\n导数大于零\n", encoding="utf-8")
        args = argparse.Namespace(job=str(self.job), file=str(path), origin="user")
        self.assertFalse(import_subtitles(args)["cached"])
        self.assertTrue(import_subtitles(args)["cached"])
        self.assertEqual(parse_subtitles(path)[0]["end"], 5.2)
        path.write_text("1\n00:10:01,000 --> 00:10:05,200\n越界\n", encoding="utf-8")
        with self.assertRaises(HandoutError): import_subtitles(args)
    def test_vtt_and_bilibili_json(self):
        path = self.root / "input.vtt"
        path.write_text("WEBVTT\n\n00:01.000 --> 00:02.000\n<b>条件</b>\n", encoding="utf-8")
        self.assertEqual(parse_subtitles(path)[0]["text"], "条件")
        path = self.root / "input.json"
        write_json(path, {"body":[{"from":1,"to":2,"content":"公式"}]})
        self.assertEqual(parse_subtitles(path)[0]["start"], 1)
    def test_partial_packet_does_not_claim_coverage(self):
        write_json(self.job / "materials/subtitles.json", self.subs)
        args = argparse.Namespace(job=str(self.job), chunk=120)
        self.assertFalse(prepare(args)["cached"])
        packet = json.loads((self.job / "model-input/chunk-001.json").read_text(encoding="utf-8"))
        self.assertEqual(packet["frames"], [])
        self.assertEqual(len(packet["subtitles"]), 3)
        self.assertTrue(prepare(args)["cached"])
    def test_public_source_link_removes_tracking_and_keeps_part(self):
        self.source["url"] = "https://www.bilibili.com/video/BV12345?p=2&session=private"
        link = source_link(self.source, 150)
        self.assertIn("p=2", link); self.assertIn("t=150", link); self.assertNotIn("private", link)
    def test_user_text_is_literal(self):
        self.assertEqual(escape(r"\input{x}"), r"\textbackslash{}input\{x\}")
    def test_malformed_identifier_is_reported_as_validation_error(self):
        self.doc["units"][0]["section_id"] = {"bad":"type"}
        self.assertFalse(self.check()["valid"])
    def test_link_part_is_inferred_when_not_explicitly_set(self):
        self.args.job = str(self.root / "linked-job")
        self.args.url = "https://www.bilibili.com/video/BV12345/?p=3"
        self.args.part = None
        result = initialize(self.args)
        self.assertEqual(result["source"]["part"], 3)
        self.assertEqual(result["source"]["video_id"], "BV12345")
    @unittest.skipUnless(importlib.util.find_spec("yt_dlp"), "optional yt-dlp not installed")
    def test_dash_only_video_can_select_video_and_audio_without_login(self):
        import yt_dlp
        from handout_media import BILIBILI_FORMAT
        item = {"id":"dash-fixture", "title":"DASH regression", "formats":[
                {"format_id":"video", "url":"https://example.com/video.mp4", "ext":"mp4", "height":1080, "vcodec":"avc1.640033", "acodec":"none"},
                {"format_id":"audio", "url":"https://example.com/audio.m4a", "ext":"m4a", "vcodec":"none", "acodec":"mp4a.40.2"}]}
        with yt_dlp.YoutubeDL({"quiet":True,"no_warnings":True,"format":BILIBILI_FORMAT}) as ydl:
            result = ydl.process_ie_result(item, download=False)
        self.assertEqual({f["format_id"] for f in result["requested_formats"]}, {"video","audio"})
    def browser_export(self):
        self.source['video_id']='BV12345_p2'
        write_json(self.job/'source.json',self.source)
        return {'status':'exported','schema_version':1,
                'source':{'bvid':'BV12345','part':2,'cid':22,'duration':600,'title':'测试课'},
                'track':{'language':'ai-zh','label':'中文自动字幕','is_ai':True},
                'body':[{'from':1,'to':3,'content':'导数为正。'}],
                'captured_at':'2026-11-01T00:00:00.000Z'}
    def test_browser_export_is_imported_with_platform_provenance(self):
        payload=self.browser_export(); path=self.root/'browser.json'; write_json(path,payload)
        args=argparse.Namespace(job=str(self.job),file=str(path))
        self.assertFalse(import_browser_subtitles(args)['cached'])
        self.assertTrue(import_browser_subtitles(args)['cached'])
        provenance=json.loads((self.job/'materials/subtitles-provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['method'],'browser_session'); self.assertTrue(provenance['is_ai'])
        self.assertEqual(provenance['cid'],22)
    def test_wrong_browser_video_or_part_is_rejected(self):
        for key,value in [('bvid','BVother'),('part',1),('duration',999)]:
            payload=self.browser_export(); payload['source'][key]=value
            with self.subTest(key=key), self.assertRaises(HandoutError): validate_browser_export(payload,self.source)
    def test_unknown_browser_fields_do_not_enter_task_materials(self):
        payload=self.browser_export(); payload['cookies']='DO_NOT_STORE'
        path=self.root/'browser.json'; write_json(path,payload)
        with self.assertRaises(HandoutError): import_browser_subtitles(argparse.Namespace(job=str(self.job),file=str(path)))
        self.assertEqual(json.loads((self.job/'materials/subtitles.json').read_text(encoding='utf-8')),[])
    def test_subtitle_login_is_distinct_from_unknown_or_available(self):
        self.assertEqual(subtitle_status({'code':0,'data':{'need_login_subtitle':True}})['status'],'waiting_login')
        self.assertEqual(subtitle_status({'code':0,'data':{}})['status'],'not_returned')
        self.assertEqual(subtitle_status({'code':-412})['status'],'read_failed')
        self.assertEqual(subtitle_status({'code':0,'data':{'subtitle':{'subtitles':[{'lan':'ai-zh','subtitle_url':'private-url'}]}}})['status'],'available')
    def test_public_probe_cannot_invalidate_an_imported_browser_transcript(self):
        payload=self.browser_export(); path=self.root/'browser.json'; write_json(path,payload)
        import_browser_subtitles(argparse.Namespace(job=str(self.job),file=str(path)))
        record_subtitle_probe(self.job,{'status':'waiting_login','method':'unauthenticated_public_probe'})
        state=json.loads((self.job/'state.json').read_text(encoding='utf-8'))
        self.assertEqual(state['resource_access']['subtitles']['status'],'ready')
        self.assertEqual(state['subtitle_checks']['unauthenticated_public_probe']['status'],'waiting_login')
    def test_av_source_checks_the_exported_aid_instead_of_guessing_bvid(self):
        payload=self.browser_export(); self.source['video_id']='av123'; payload['source']['aid']=123
        self.assertEqual(validate_browser_export(payload,self.source)['source']['bvid'],'BV12345')
        payload['source']['aid']=124
        with self.assertRaises(HandoutError): validate_browser_export(payload,self.source)


if __name__ == "__main__": unittest.main()
