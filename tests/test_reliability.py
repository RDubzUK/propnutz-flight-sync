"""Known-answer checks for the local reliability milestone; no user media."""
import copy
import json
import math
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import numpy as np

from fpv_audio_pairing import matching, review, projects, store, quality, export_jobs
from fpv_audio_pairing.cache import get_or_extract
from fpv_audio_pairing.evidence import assess_audio_pair
from fpv_audio_pairing.fingerprint import _landmarks, _segment_features, validate_audio
from fpv_audio_pairing.exports import export_pair
from fpv_audio_pairing.metadata import probe_video
from fpv_audio_pairing.search import run_match
from fpv_audio_pairing.web import MatchOptions, ExportOptions


def record(kind, name, duration=60, mtime=1000):
    return {"id": uuid.uuid4().hex, "kind": kind, "name": name, "path": name, "signature": [10, 1], "mtime": mtime,
            "filename_time": mtime-duration, "metadata": {"duration": duration, "fps": 30., "width": 160, "height": 90,
                                                         "has_audio": True, "codec": "h264"}}


def session(records, pairs=()):
    return {"id": uuid.uuid4().hex, "name": "Known answer", "created": 1, "folders": {"fpv": "/fpv", "stick": "/stick"},
            "videos": records, "pairs": list(pairs), "exports": [], "clocks": [], "clock_warnings": []}


def fingerprint(seed=1, offset=0):
    rng = np.random.default_rng(seed)
    samples = rng.normal(0, .03, 30*8000)
    at = np.arange(len(samples))/8000
    for i in range(60):
        begin=i*.5; mask=(at>=begin)&(at<begin+.5)
        samples[mask] += rng.uniform(.03,.5)*np.sin(2*np.pi*rng.uniform(150,2500)*at[mask])
    times, features = _segment_features(samples, offset)
    hashes, hash_times = _landmarks(samples, offset)
    _, inv, counts = np.unique(hashes,return_inverse=True,return_counts=True)
    keep=counts[inv]<=8
    median=np.median(features,axis=0)
    scale=np.maximum(np.percentile(abs(features-median),75,axis=0)*1.4826,1e-5)
    return {"time":times,"features":np.clip((features-median)/scale,-5,5),"segments":np.zeros(len(times),np.int32),
            "valid":np.ones(len(times),bool),"quality":np.asarray(1.),"duration":np.asarray(30.+offset),
            "hashes":hashes[keep],"hash_times":hash_times[keep]}


class Isolated(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.previous=store.ROOT;store.ROOT=self.root/'data'

    def tearDown(self):
        store.ROOT=self.previous;self.temp.cleanup()


class AlignmentTests(Isolated):
    def test_complete_overlap_is_not_audio_span(self):
        self.assertEqual(matching.overlap(300,1000,42),{"fpv_start":0.,"radio_start":42,"overlap_duration":300})
        self.assertEqual(matching.overlap(300,1000,-20)["overlap_duration"],280)

    def test_modified_date_tolerance_and_audio_independence(self):
        f=record('fpv','f',60,1000);s=record('stick','s',60,1100)
        p=matching.make_pair(f,s,0,confirmed=True,method='audio')
        f2=record('fpv','f2',60,2000);s2=record('stick','s2',60,2104)
        q=matching.make_pair(f2,s2,0,method='audio',confidence='Strong')
        doc=session([f,s,f2,s2],[p,q]);matching.suggest(doc)
        self.assertTrue(next(x for x in q['clock_support'] if x['method']=='modified')['agrees'])
        doc['modified_tolerance']=2;matching.suggest(doc)
        self.assertFalse(next(x for x in q['clock_support'] if x['method']=='modified')['agrees'])
        self.assertEqual(q['confidence'],'Strong')

    def test_date_only_confirmation_does_not_reinforce_clock(self):
        f,s=record('fpv','f'),record('stick','s',mtime=1100)
        p=matching.make_pair(f,s,0,confirmed=True,method='timestamp')
        doc=session([f,s],[p]);self.assertIsNone(matching.clock_model(doc,'modified'))
        p['verification']='independent';self.assertIsNotNone(matching.clock_model(doc,'modified'))

    def test_inconsistent_independent_clocks_stay_disabled(self):
        records=[record('fpv','f'),record('stick','s',mtime=1100),record('fpv','f2'),record('stick','s2',mtime=1120)]
        pairs=[matching.make_pair(records[i],records[i+1],0,confirmed=True,method='manual') for i in (0,2)]
        self.assertFalse(matching.clock_model(session(records,pairs),'modified')['consistent'])

    def test_drift_check_and_local_coverage(self):
        p={'offset':2.,'overlap_duration':100.,'sync_points':[{'fpv_time':0.,'stick_time':2.},{'fpv_time':100.,'stick_time':102.3}]}
        self.assertEqual(review.sync_check(p)['status'],'drift')
        p['sync_points'][1]['stick_time']=102.;self.assertEqual(review.sync_check(p)['status'],'checked')
        p['sync_points'][1]={'fpv_time':10.,'stick_time':12.};self.assertEqual(review.sync_check(p)['status'],'limited')

    def test_flight_gaps_and_owner_conflicts(self):
        f1,f2,s,s2=record('fpv','a',10),record('fpv','b',10),record('stick','s',60),record('stick','s2',60)
        ps=[matching.make_pair(f1,s,0,confirmed=True),matching.make_pair(f2,s,15,confirmed=True),matching.make_pair(f1,s2,0,confirmed=True)]
        g=review.flights(session([f1,f2,s,s2],ps))[0]
        self.assertEqual(g['gaps'],[{'start':10.,'end':15.}]);self.assertTrue(g['parts'][0]['conflict'])

    def test_summary_distinguishes_unsearched_and_unmatched(self):
        f1,f2=record('fpv','a'),record('fpv','b');f2['match_checked']=1
        counts=review.summary(session([f1,f2]));self.assertEqual(counts['unsearched'],1);self.assertEqual(counts['unmatched'],1)


class PersistenceTests(Isolated):
    def test_structurally_invalid_json_offers_backup(self):
        doc=session([]);store.write(doc);store.checkpoint(doc['id'],force=True)
        (store.directory(doc['id'])/'session.json').write_text('{}')
        self.assertTrue(store.read(doc['id'])['recovery_required'])
        self.assertEqual(len(store.sessions()),1)

    def test_second_process_cannot_share_data_folder(self):
        import sys
        previous=store._INSTANCE
        store.acquire_instance()
        try:
            result=subprocess.run([sys.executable,'-c',f'from pathlib import Path; from fpv_audio_pairing import store; store.ROOT=Path({str(store.ROOT)!r}); store.acquire_instance()'],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'Another Flight Sync instance',result.stderr)
        finally:
            store._INSTANCE.close();store._INSTANCE=previous

    def test_transient_windows_rename_is_retried(self):
        a=self.root/'pending.json';b=self.root/'target.json';a.write_text('{}')
        error=PermissionError('test sharing lock');error.winerror=5
        with patch.object(store.os,'replace',side_effect=[error, None]) as replace, patch.object(store.time,'sleep'):
            store._replace_session(a,b);self.assertEqual(replace.call_count,2)
        self.assertTrue(a.exists())  # Mock did not actually replace it.

    def test_backup_and_recovery_keep_original(self):
        doc=session([]);store.write(doc);doc['name']='Updated';store.write(doc)
        self.assertEqual(store.read(doc['id'])['name'],'Updated')
        current=store.directory(doc['id'])/'session.json';current.write_text('{bad')
        fallback=store.read(doc['id']);self.assertTrue(fallback['recovery_required'])
        with self.assertRaises(store.SessionSaveError):store.write(fallback)
        restored=store.restore(doc['id'],fallback['recovery_required']);self.assertEqual(restored['name'],'Known answer')
        self.assertTrue(list(current.parent.glob('before-restore-*.json')))

    def test_identity_cache_survives_move_and_modified_date_change(self):
        source=self.root/'a.mp4';source.write_bytes(b'x'*1000)
        identity=projects.content_id(source);cache=self.root/'cache';calls=[]
        def extract():calls.append(1);return {'sample':np.arange(10)}
        a=get_or_extract(str(source),cache,'audio','v1',{},extract,identity=identity)
        moved=self.root/'b.mp4';shutil.copyfile(source,moved)
        b=get_or_extract(str(moved),cache,'audio','v1',{},extract,identity=projects.content_id(moved))
        self.assertEqual(len(calls),1);np.testing.assert_equal(a['sample'],b['sample'])

    def test_project_import_is_new_session_without_external_jobs_or_exports(self):
        f=record('fpv','a');s=record('stick','b');doc=session([f,s],[matching.make_pair(f,s,2,method='manual',confidence='Manual')])
        doc.update(job={'resume':{'kind':'export','directory':'/untrusted'}},exports=[{'directory':'/untrusted'}])
        payload=projects.document(doc);opened=projects.open_project(json.dumps(payload).encode())
        self.assertNotEqual(opened['id'],doc['id']);self.assertNotIn('job',opened);self.assertEqual(opened['exports'],[])
        self.assertTrue(opened['pairs'][0]['stale'])

    def test_invalid_project_is_rejected(self):
        with self.assertRaises(ValueError):projects.open_project(b'[]')

    def test_relink_preserves_clock_dates_and_confirmed_alignment(self):
        roots={k:str(self.root/k) for k in ['fpv','stick']};records=[]
        for kind in roots:
            Path(roots[kind]).mkdir();path=Path(roots[kind])/'a.mp4';path.write_bytes(kind.encode()*100)
            r=record(kind,'a.mp4');r.update(path=str(path),signature=[path.stat().st_size,path.stat().st_mtime_ns],content_id=projects.content_id(path))
            records.append(r)
        doc=session(records,[matching.make_pair(*records,2,confirmed=True,method='manual')]);doc['folders']=roots
        new={k:str(self.root/(k+'-moved')) for k in roots}
        for kind in roots:shutil.copytree(roots[kind],new[kind])
        with patch('fpv_audio_pairing.metadata.probe_video',return_value=records[0]['metadata']):
            relinked=projects.relink(doc,new,lambda *_:None,threading.Event())
        self.assertTrue(relinked['pairs'][0]['confirmed']);self.assertFalse(relinked['pairs'][0]['stale'])
        self.assertEqual(relinked['videos'][0]['mtime'],1000)


class AudioTests(Isolated):
    @classmethod
    def setUpClass(cls):
        cls.fpv=fingerprint(1);cls.stick=fingerprint(1,3.2);cls.wrong=fingerprint(2)

    def test_known_audio_offset_and_nonmatch(self):
        validate_audio(self.fpv)
        e=assess_audio_pair(copy.deepcopy(self.stick),copy.deepcopy(self.fpv))
        self.assertTrue(e['eligible'],e['reasons']);self.assertAlmostEqual(e['offset'],3.2,places=1)
        self.assertFalse(assess_audio_pair(copy.deepcopy(self.wrong),copy.deepcopy(self.fpv))['eligible'])

    def test_benchmark_measures_known_answers(self):
        f,s,w=record('fpv','f'),record('stick','s'),record('stick','w')
        doc=session([f,s,w]);doc['references']=[{'id':'positive','fpv':f['id'],'stick':s['id'],'match':True,'expected_offset':3.2},
                                              {'id':'negative','fpv':f['id'],'stick':w['id'],'match':False}]
        data={f['id']:self.fpv,s['id']:self.stick,w['id']:self.wrong}
        result=quality.benchmark(doc,lambda r,b:copy.deepcopy(data[r['id']]),30,lambda *_:None,threading.Event())
        self.assertEqual(result['counts']['true_positive'],1);self.assertEqual(result['counts']['true_negative'],1)

    def test_positive_only_collection_does_not_claim_precision(self):
        f,s=record('fpv','f'),record('stick','s');doc=session([f,s])
        doc['references']=[{'id':'positive','fpv':f['id'],'stick':s['id'],'match':True,'expected_offset':None}]
        result=quality.benchmark(doc,lambda r,b:copy.deepcopy(self.fpv if r['kind']=='fpv' else self.stick),30,lambda *_:None,threading.Event())
        self.assertEqual(result['counts']['true_positive'],1);self.assertIsNone(result['precision'])
        self.assertEqual(result['timing_references'],0)

    def test_wider_samples_keep_best_evidence_and_later_decision(self):
        f,s=record('fpv','f'),record('stick','s');doc=session([f,s]);store.write(doc)
        base={'eligible':False,'offset':3.2,'best_offset':3.2,'quality':1,'reasons':['Needs review']}
        evidence=[dict(base,best_score=.9),dict(base,best_score=.5)]
        options=MatchOptions(adaptive=True,retry_limit=60)
        with patch('fpv_audio_pairing.search.assess_audio_pair',side_effect=evidence), patch('fpv_audio_pairing.search.audio_sections',return_value={'windows':[]}):
            run_match(doc['id'],options,lambda *_:None,threading.Event(),lambda r,b:{},lambda v:v)
        saved=store.read(doc['id']);pair=saved['pairs'][0]
        self.assertEqual(pair['score'],.9);self.assertEqual(pair['audio_boundary'],30)
        pair.update(review_state='later',offset=4.);saved['decisions']={pair['id']:'later'};store.write(saved)
        run_match(doc['id'],options,lambda *_:None,threading.Event(),lambda r,b:self.fail('Saved comparisons should be reused'),lambda v:v)
        pair=store.read(doc['id'])['pairs'][0]
        self.assertEqual(pair['review_state'],'later');self.assertEqual(pair['offset'],4.)

    def test_adaptive_search_reuses_comparisons_and_keeps_rejection(self):
        f,s=record('fpv','f'),record('stick','s');doc=session([f,s]);pid=matching.pair_id(f['id'],s['id'])
        doc['decisions']={pid:'rejected'};store.write(doc);calls=[]
        def load(r,b):calls.append((r['id'],b));return copy.deepcopy(self.fpv if r['kind']=='fpv' else self.stick)
        run_match(doc['id'],MatchOptions(adaptive=True,retry_limit=60),lambda *_:None,threading.Event(),load,lambda v:v)
        self.assertEqual(store.read(doc['id'])['pairs'][0]['review_state'],'rejected')
        before=len(calls);run_match(doc['id'],MatchOptions(adaptive=True,retry_limit=60),lambda *_:None,threading.Event(),load,lambda v:v)
        self.assertEqual(len(calls),before)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class ExportTests(Isolated):
    def test_resume_key_is_independent_of_pair_order(self):
        a={'id':'a','offset':1,'source_signatures':{'fpv':[1,2]},'overlap_duration':5}
        b={'id':'b','offset':2,'source_signatures':{'fpv':[3,4]},'overlap_duration':10}
        self.assertEqual(export_jobs.alignment_key([a,b]),export_jobs.alignment_key([b,a]))

    def test_accurate_and_copy_cuts_keep_different_native_rates(self):
        sources={}
        for kind,fps in [('radio',24),('fpv',30)]:
            path=self.root/f'{kind}.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'testsrc2=size=160x90:rate={fps}:duration=6',
                            '-c:v','libx264','-threads','1','-g','48','-pix_fmt','yuv420p',str(path)],check=True)
            sources[kind]=(path,probe_video(path))
        info={'radio_start':.73,'fpv_start':.21,'overlap_duration':3.5,'source_metadata':{k:v[1] for k,v in sources.items()}}
        for profile in ['h264','copy']:
            result=export_pair(info,sources['radio'][0],sources['fpv'][0],self.root/profile,profile=profile)
            self.assertEqual(result['export_fps'],'original')
            for kind,fps in [('StickCam',24),('FPV',30)]:
                fraction=result['output_timing'][kind]['avg_frame_rate'];a,b=map(int,fraction.split('/'))
                self.assertAlmostEqual(a/b,fps);self.assertLess(abs(result['output_timing'][kind]['duration']-3.5),.13)


if __name__=='__main__':unittest.main()
