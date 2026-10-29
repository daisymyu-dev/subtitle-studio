import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from studio.sentence_study import prepare_sentences, load_sentence_data
except ImportError:
    prepare_sentences = load_sentence_data = None


class SentenceStudyTests(unittest.TestCase):
    def setUp(self):
        work=Path(__file__).resolve().parents[1]/'.work/tmp'
        work.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.id='a'*32
        self.job=self.root/'results'/self.id;self.job.mkdir(parents=True)
        self.cues=[{'start':0,'end':2,'text':'This is one.'},{'start':2,'end':4,'text':'This is two.'}]
        self.result={'id':self.id,'title':'Example','url':'https://youtu.be/BaW_jenozKc','language':'en','source':'platform_auto','count':2,'warning':'Source may contain errors.','files':{ext:'Example.'+ext for ext in ('srt','vtt','txt')}}
        from studio.subtitles import Cue,render_subtitles
        for ext in self.result['files']:(self.job/('Example.'+ext)).write_text(render_subtitles([Cue(**x) for x in self.cues],ext),'utf-8')
        (self.job/'study-cues.json').write_text(json.dumps(self.cues),'utf-8')
        (self.job/'metadata.json').write_text(json.dumps(self.result),'utf-8')
        self.translations=[]
        class Translator:
            def translate_many(inner,texts,progress=None):
                self.translations.extend(texts)
                return ['第一句。' if 'one' in x else '第二句。' for x in texts]
        self.translator=Translator()

    def test_prepares_and_caches_one_translation_per_sentence_preserving_raw(self):
        self.assertTrue(callable(prepare_sentences),'sentence preparation must exist')
        raw=(self.job/'study-cues.json').read_bytes()
        updated=prepare_sentences(self.root,self.id,translator=self.translator,punctuator=lambda text:[])
        self.assertEqual(self.translations,['This is one.','This is two.'])
        self.assertEqual(updated['sentence_version'],1)
        data=load_sentence_data(self.root,self.id)
        self.assertEqual([x['chinese'] for x in data['cues']],['第一句。','第二句。'])
        self.assertEqual(raw,(self.job/'study-cues.json').read_bytes())
        self.assertFalse(list(self.job.glob('*.docx')))
        prepare_sentences(self.root,self.id,translator=self.translator,punctuator=lambda text:(_ for _ in ()).throw(AssertionError('no repeat punctuation')))
        self.assertEqual(len(self.translations),2)

    def test_never_reuses_an_old_paragraph_translation_for_individual_sentences(self):
        self.assertTrue(callable(prepare_sentences),'sentence preparation must exist')
        (self.job/'bilingual.json').write_text(json.dumps({'blocks':[{'start':0,'end':4,'english':'This is one. This is two.','chinese':'这是旧的整段翻译。'}],'chinese_source':'legacy'}),'utf-8')
        prepare_sentences(self.root,self.id,translator=self.translator,punctuator=lambda text:[])
        self.assertEqual(len(self.translations),2)
        self.assertNotIn('这是旧的整段翻译。',[x['chinese'] for x in load_sentence_data(self.root,self.id)['cues']])

    def test_existing_sentence_punctuation_does_not_load_or_download_a_model(self):
        from types import SimpleNamespace
        def fail(*args,**kwargs):raise AssertionError('already punctuated source needs no model')
        with patch.dict('sys.modules',{'studio.punctuation':SimpleNamespace(punctuation_marks=fail)}):
            prepare_sentences(self.root,self.id,translator=self.translator)
        self.assertEqual(len(self.translations),2)

    def test_legacy_results_with_only_retained_srt_can_upgrade_without_extraction(self):
        (self.job/'study-cues.json').unlink()
        prepare_sentences(self.root,self.id,translator=self.translator,punctuator=lambda text:[])
        self.assertEqual(len(load_sentence_data(self.root,self.id)['cues']),2)
        self.assertFalse((self.job/'study-cues.json').exists())

    def test_tampered_source_or_partial_translations_cannot_be_loaded_or_exported(self):
        self.assertTrue(callable(prepare_sentences),'sentence preparation must exist')
        prepare_sentences(self.root,self.id,translator=self.translator,punctuator=lambda text:[])
        changed=copy.deepcopy(self.cues);changed[0]['text']='Other words.'
        (self.job/'study-cues.json').write_text(json.dumps(changed),'utf-8')
        with self.assertRaises(Exception):load_sentence_data(self.root,self.id)

    def test_sentence_word_export_uses_exact_same_units_without_network(self):
        self.assertTrue(callable(prepare_sentences),'sentence preparation must exist')
        prepare_sentences(self.root,self.id,translator=self.translator,punctuator=lambda text:[])
        from studio.study_export import export_study_word
        written=[]
        def writer(path,title,url,blocks,*notes):
            written.extend(blocks);Path(path).write_bytes(b'DOCX test')
        result=export_study_word(self.root,self.id,word_writer=writer,desktop_dir=self.root/'Desktop')
        self.assertEqual([x['english'] for x in written],['This is one.','This is two.'])
        self.assertEqual([x['chinese'] for x in written],['第一句。','第二句。'])
        self.assertTrue(Path(result['desktop_path']).exists())

    def test_new_sentence_study_pipeline_does_not_first_translate_old_paragraphs(self):
        from studio.service import Pipeline,validate_options
        self.assertIs(validate_options({'sentence_study':True,'bilingual_study':True}).get('sentence_study'),True)
        class Tools:
            def metadata(inner,*args,**kwargs):return {'title':'Example','language':'en','duration':4,'subtitles':{'en':[{'ext':'vtt','url':'https://www.youtube.com/api/timedtext?lang=en'}]}}
            def caption(inner,*args):return (self.job/'Example.vtt').read_text('utf-8')
        with patch('studio.sentence_study.prepare_sentences',return_value={**self.result,'sentence_version':1}) as prepare:
            result=Pipeline(self.root,Tools(),translator=self.translator).process('youtube',self.result['url'],{'bilingual_study':True,'sentence_study':True})
        self.assertEqual(result['sentence_version'],1)
        self.assertEqual(self.translations,[])
        self.assertEqual(prepare.call_count,1)

    def test_video_and_original_audio_study_endpoint_returns_the_same_sentence_pairs(self):
        self.assertTrue(callable(prepare_sentences),'sentence preparation must exist')
        prepare_sentences(self.root,self.id,translator=self.translator,punctuator=lambda text:[])
        from studio.shadowing import ShadowingStore
        store=ShadowingStore(self.root)
        self.addCleanup(store.close)
        data=store.load_study(self.id)
        self.assertEqual(data.get('mode'),'sentences')
        self.assertEqual([(x['english'],x['chinese']) for x in data['cues']],[('This is one.','第一句。'),('This is two.','第二句。')])


if __name__=='__main__':unittest.main()
