import json
from pathlib import Path
import tempfile
import unittest

from studio.learning_store import LearningStore


class LearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.store=LearningStore(self.root)

    def test_known_saved_neutral_are_persistent_and_exclusive(self):
        data={'key':'bifurcated','term':'bifurcated','state':'learn','english':'The response is bifurcated.','chinese':'反应两极分化。','start':12}
        self.store.set_term(data)
        self.assertEqual(LearningStore(self.root).profile()['saved'][0]['key'],'bifurcated')
        self.store.set_term({'key':'bifurcated','term':'bifurcated','state':'known'})
        self.assertEqual(self.store.profile()['known'],['bifurcated']);self.assertEqual(self.store.profile()['saved'],[])
        self.store.set_term({'key':'bifurcated','term':'bifurcated','state':'neutral'})
        self.assertEqual(self.store.profile()['known'],[])

    def test_invalid_values_do_not_mutate_profile(self):
        for change in ({'state':'invalid'},{'key':'../x'},{'key':'A\nB'},{'url':'javascript:alert(1)'},{'start':True},{'english':'x'*4001}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.store.set_term({'key':'word','term':'word','state':'learn',**change})
        self.assertEqual(self.store.profile()['saved'],[])

    def test_progress_requires_existing_confined_metadata(self):
        job='a'*32;folder=self.root/'results'/job;folder.mkdir(parents=True)
        (folder/'metadata.json').write_text(json.dumps({'id':job,'title':'Self-authored example','url':None,'count':3,'created_at':'2026-01-01T00:00:00Z'}))
        self.store.set_progress(job,12.5)
        self.assertEqual(LearningStore(self.root).profile()['progress'][job],12.5)
        self.assertEqual(self.store.history()[0]['position'],12.5)
        self.assertEqual(self.store.history()[0]['title'],'Self-authored example')
        for identity,value in [('bad',1),('b'*32,1),(job,float('nan')),(job,True),(job,-1)]:
            with self.assertRaises(ValueError):self.store.set_progress(identity,value)

    def test_history_excludes_bad_or_foreign_metadata_and_private_paths(self):
        base=self.root/'results';base.mkdir()
        for job,data in [('a'*32,{'id':'a'*32,'title':'Good','count':1,'output_dir':'private/path'}),('b'*32,{'id':'c'*32,'title':'Wrong'}),('not-a-job',{'id':'not-a-job'})]:
            directory=base/job;directory.mkdir();(directory/'metadata.json').write_text(json.dumps(data))
        items=self.store.history();self.assertEqual(len(items),1);self.assertNotIn('output_dir',items[0])

    def test_parameterized_storage_accepts_literal_text_without_execution(self):
        self.store.set_term({'key':'example','term':'example','state':'learn','english':"Literal <img src=x> '; DROP TABLE terms;"})
        self.assertIn('DROP TABLE',self.store.profile()['saved'][0]['english'])

