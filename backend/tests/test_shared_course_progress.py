import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch
from app.services import plans

class SharedCourseProgressTests(unittest.TestCase):
 def test_same_course_shares_status_only_in_one_roadmap(self):
  acts=[{'id':'one','res':'c','skill':'SQL'},{'id':'two','res':'c','skill':'Python'},{'id':'book','res':'b'},{'id':'task','res':'c','task':True}]
  row={'roadmap_id':'roadmap','project_id':1,'status':'IN_PROGRESS','content':{'acts':acts}}
  tx=Mock();tx.one.side_effect=[{'content':row['content']}, *[{'memo':'own note','attachment':{'id':'old'}}]*2];tx.val.return_value='IN_PROGRESS'
  with patch.object(plans,'_owned',return_value=row),patch.object(plans,'record',return_value={}),patch.object(plans.db,'tx',return_value=nullcontext(tx)),patch.object(plans.catalog,'items',return_value={'c':{'type':'course'}}):
   plans.save_progress(1,'roadmap','one',{'status':'done','memo':'new note'})
  inserts=[c.kwargs for c in tx.run.call_args_list if 'INSERT INTO' in c.args[0]]
  self.assertEqual([c['a'] for c in inserts],['one','two'])
  self.assertEqual([c['s'] for c in inserts],['done','done'])
  self.assertEqual([c['m'] for c in inserts],['new note','own note'])
  self.assertTrue(all(c['r']=='roadmap' for c in inserts))

 def test_books_do_not_share_completion(self):
  row={'roadmap_id':'roadmap','project_id':1,'status':'IN_PROGRESS','content':{'acts':[{'id':'one','res':'b'},{'id':'two','res':'b'}]}}
  tx=Mock();tx.one.side_effect=[{'content':row['content']}, {}];tx.val.return_value='IN_PROGRESS'
  with patch.object(plans,'_owned',return_value=row),patch.object(plans,'record',return_value={}),patch.object(plans.db,'tx',return_value=nullcontext(tx)),patch.object(plans.catalog,'items',return_value={'b':{'type':'book'}}):
   plans.save_progress(1,'roadmap','one',{'status':'done'})
  self.assertEqual([c.kwargs['a'] for c in tx.run.call_args_list if 'INSERT INTO' in c.args[0]],['one'])
