"""Provider units, incomplete curricula and explicit timetable estimates."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

from src.database.course_duration import normalize, positive_seconds, full_curriculum
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from app.course_time import effective


class CourseDurationTests(unittest.TestCase):
    def test_provider_units_are_not_weeks(self):
        for source,payload,seconds,kind in [
            ('API_MS_LEARN',{'duration_in_minutes':71},4260,'learning'),
            ('API_KMOOC',{'course_playtime':43200,'vod_playtime':31585},43200,'learning'),
            ('API_KMOOC',{'course_playtime':'0','vod_playtime':41677},41677,'video'),
            ('WEB_STEP',{'edutime':'20'},72000,'learning')]:
            with self.subTest(source=source):
                value=normalize(source,payload)
                self.assertEqual((value['duration_seconds'],value['duration_kind']),(seconds,kind))
                self.assertIsNone(value['estimated_duration_seconds'])

    def test_inflearn_video_sum_excludes_text_and_requires_complete_video_times(self):
        lessons=[{'id':1,'hasVideo':True,'runtime':540},{'id':2,'hasVideo':False,'runtime':0}]
        self.assertEqual(normalize('WEB_INFLEARN',{'lessons':lessons})['duration_seconds'],540)
        lessons.append({'id':3,'hasVideo':True,'runtime':0})
        result=normalize('WEB_INFLEARN',{'lessons':lessons})
        self.assertIsNone(result['duration_seconds'])
        self.assertEqual(result['estimated_duration_seconds'],540+540)
        self.assertEqual(result['duration_provenance']['status'],'partial')

    def test_curriculum_estimate_is_distinct_from_confirmed_time(self):
        for source,payload,seconds in [
            ('WEB_KOCW',{'lessons':[{'video_listed':True}]*10},30000),
            ('WEB_OPENTUTORIALS',{'lessons':[{'video_embed_present':True}]*3},3600)]:
            value=normalize(source,payload,curriculum={'curriculum_lesson_count':3,'curriculum_html_sha256':'fixture'} if source=='WEB_OPENTUTORIALS' else None)
            self.assertIsNone(value['duration_seconds'])
            self.assertEqual(value['estimated_duration_seconds'],seconds)
            api=effective(value,{'hours':1,'estimated_fields':['hours','stage']})
            self.assertEqual(api['hours'],seconds/3600)
            self.assertEqual(api['timeStatus'],'estimated')
            self.assertIn('총시간 미확보',api['timeNote'])

    def test_zero_boolean_nonfinite_and_invalid_values_do_not_become_official_time(self):
        for value in (None,0,-1,True,'invalid','NaN','Infinity',{},2**32):
            self.assertIsNone(positive_seconds(value))
        self.assertEqual(positive_seconds('1.5',3600),5400)
        self.assertEqual(normalize(None,{})['estimated_duration_seconds'],7200)

    def test_legacy_one_hour_is_replaced_but_manual_hours_survive(self):
        value=normalize('WEB_STEP',{'edutime':'20'})
        old={'hours':1,'estimated_fields':['hours','stage']}
        self.assertEqual(effective(value,old)['hours'],20)
        self.assertNotIn('hours',effective(value,old)['estimated'])
        for origin,fields in [('legacy',[]),('manual',['hours'])]:
            api=effective(value,{'hours':7,'hours_origin':origin,'estimated_fields':fields})
            self.assertEqual((api['hours'],api['timeStatus']),(7,'manual'))
        api=effective(value,{'hours':1,'hours_origin':'catalog','estimated_fields':[]})
        self.assertEqual(api['hours'],20)

    def test_duplicate_videos_never_claim_a_confirmed_total(self):
        lesson={'id':1,'hasVideo':True,'runtime':300}
        result=normalize('WEB_INFLEARN',{'lessons':[lesson,lesson]})
        self.assertIsNone(result['duration_seconds'])
        self.assertTrue(result['duration_provenance']['duplicate_video_ids'])

    def test_kocw_fragments_share_numbered_chapter_and_suspended_video_is_excluded(self):
        lessons=[{'chapter':'1.','video_listed':True}, {'chapter':'','video_listed':True},
                 {'chapter':'1.','video_listed':True}, {'chapter':'2.','video_listed':True},
                 {'chapter':'3.','video_listed':True,'suspended_marker':True}]
        result=normalize('WEB_KOCW',{'lessons':lessons})
        self.assertEqual(result['estimated_duration_seconds'],2*50*60)
        self.assertEqual(result['duration_provenance']['video_count'],4)
        self.assertEqual(result['duration_provenance']['lesson_count'],2)

    def test_inflearn_imputes_only_missing_videos_from_same_course_median(self):
        lessons=[{'id':i,'hasVideo':True,'runtime':seconds} for i,seconds in enumerate([60,120,900,0])]
        result=normalize('WEB_INFLEARN',{'lessons':lessons})
        self.assertIsNone(result['duration_seconds'])
        self.assertEqual(result['estimated_duration_seconds'],1080+120)
        self.assertEqual(result['duration_provenance']['imputed_video_seconds'],120)

    def test_full_outline_cache_and_restored_proof_do_not_use_sample_count(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder)
            raw=b'<a href="/course/1223/1">one</a><a href="/course/1223/2">two</a><a href="/course/1223/3">three</a><a href="/course/1223/3">duplicate</a>'
            (root/'outline.html').write_bytes(raw)
            payload={'html_path':'outline.html','html_sha256':hashlib.sha256(raw).hexdigest(),'source_id':1223,'lessons':[{'video_embed_present':True}]}
            proof=full_curriculum(payload,{},root)
            self.assertEqual(proof['curriculum_lesson_count'],3)
            self.assertEqual(normalize('WEB_OPENTUTORIALS',payload,curriculum=proof)['estimated_duration_seconds'],3600)
            (root/'outline.html').unlink()
            self.assertEqual(full_curriculum(payload,proof,root),proof)
            (root/'outline.html').write_bytes(b'changed')
            with self.assertRaises(ValueError):full_curriculum(payload,{},root)


if __name__=='__main__':unittest.main()
