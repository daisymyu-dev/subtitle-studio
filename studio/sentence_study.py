"""Explicit full-sentence learning, with unchanged raw captions and local punctuation."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import threading

from .bilingual import GoogleWebTranslator, TranslationError
from .service import UserError
from .subtitles import Cue, normalize_youtube_url, render_subtitles

VERSION=1
NOTE='逐句中英对照；补标点由本地模型估计，不改原话。句内时间由原字幕估算，非逐词对齐；截断内容标为残句。'


def _error():
    return UserError('sentence_data','逐句学习数据缺失、损坏或与原文不一致，无法保证全文；请保留原文件并重新整理。')


def _source(store,job_id):
    from .study_export import _times, _text, _safe_name, _ENGLISH
    result=store.read('metadata.json')
    if not isinstance(result,dict) or not isinstance(result.get('files'),dict):raise _error()
    if store.checked(store.job/'study-cues.json').exists():cues=store.read('study-cues.json')
    else:
        from .shadowing import _parse_srt
        name=_safe_name(result['files'].get('srt'))
        if Path(name).suffix.lower()!='.srt':raise _error()
        cues=_parse_srt(store.content(name))
    if (not isinstance(result,dict) or result.get('id')!=job_id or result.get('language')!='en'
            or result.get('source') not in _ENGLISH or not isinstance(result.get('files'),dict)
            or not isinstance(cues,list) or not cues or type(result.get('count')) is not int
            or result['count']!=len(cues)):
        raise _error()
    _text(result.get('title'));_text(result.get('warning'))
    try:result['url']=normalize_youtube_url(result.get('url',''))
    except (ValueError,TypeError):raise _error() from None
    for cue in cues:_times(cue);_text(cue.get('text'))
    for extension,name in result['files'].items():
        if extension not in ('srt','vtt','txt','docx'):raise _error()
        _safe_name(name)
        if Path(name).suffix.lower()!='.'+extension:raise _error()
        store.file(store.job/name)
    if not {'srt','vtt','txt'}.issubset(result['files']):raise _error()
    for extension in ('srt','vtt','txt'):
        if store.content(result['files'][extension]).replace('\r\n','\n')!=render_subtitles([Cue(**cue) for cue in cues],extension):raise _error()
    result['output_dir']=str(store.job.resolve())
    fingerprint=sha256(json.dumps(cues,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    return result,cues,fingerprint


def _validated(store,result,cues,fingerprint):
    from .sentences import validate_sentences
    data=store.read('sentence-study.json')
    if (not isinstance(data,dict) or data.get('version')!=VERSION or data.get('source_sha256')!=fingerprint
            or not isinstance(data.get('rows'),list) or not data['rows']
            or not isinstance(data.get('chinese_source'),str) or not data['chinese_source'].strip()):raise _error()
    try:validate_sentences(cues,data['rows'])
    except (ValueError,TypeError,KeyError,OverflowError):raise _error() from None
    for row in data['rows']:
        if not isinstance(row.get('chinese'),str) or not row['chinese'].strip():raise _error()
    return data


def load_sentence_data(root,job_id):
    from .study_export import _Retained
    if not isinstance(job_id,str) or not re.fullmatch(r'[a-f0-9]{32}',job_id):raise ValueError('任务编号无效。')
    store=_Retained(root,job_id);result,cues,fingerprint=_source(store,job_id)
    data=_validated(store,result,cues,fingerprint)
    return {'id':job_id,'title':result['title'],'url':result['url'],'mode':'sentences',
            'cues':data['rows'],'chinese_note':NOTE+' 来源：'+data['chinese_source']}


def _publish(store,name,data):
    target=store.checked(store.job/name);staged=None;identity=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=store.work(),prefix='.sentence-',suffix='.tmp',delete=False) as output:
            staged=Path(output.name);identity=os.fstat(output.fileno())
            json.dump(data,output,ensure_ascii=False,allow_nan=False,indent=2);output.flush();os.fsync(output.fileno())
        store.file(staged);store.checked(target);os.replace(staged,target)
    finally:
        if staged is not None:store.remove_owned(staged,identity)


def prepare_sentences(root,job_id,*,translator=None,punctuator=None,report=lambda *args,**kwargs:None):
    from .study_export import _Retained
    from .sentences import build_sentences,source_text,validate_sentences
    if not isinstance(job_id,str) or not re.fullmatch(r'[a-f0-9]{32}',job_id):raise ValueError('任务编号无效。')
    store=_Retained(root,job_id)
    with store.locked():
        result,cues,fingerprint=_source(store,job_id)
        if store.checked(store.job/'sentence-study.json').exists():
            data=_validated(store,result,cues,fingerprint)
        else:
            report('sentences','正在合并完整句子；缺失标点由本地模型估计，不改原话。')
            text=source_text(cues)
            preliminary=build_sentences(cues)
            needs_restoration=any('missing_terminal_punctuation' in row['fragment_reason'] or len(row['english'].split())>80 for row in preliminary)
            if punctuator is None and needs_restoration:
                from .punctuation import punctuation_marks
                marks=punctuation_marks(text,root=root,report=report)
            else:marks=punctuator(text) if punctuator else []
            rows=build_sentences(cues,marks=marks)
            validate_sentences(cues,rows)
            report('translating','正在逐句翻译，每句英文只配自己的中文译文。')
            try:
                translations=(translator or GoogleWebTranslator()).translate_many([row['english'] for row in rows],
                    lambda done,total:report('translating',f'正在逐句翻译：{done} / {total} 句。',translated=done,translation_total=total))
            except TranslationError as error:raise UserError('translation',str(error)) from None
            if len(translations)!=len(rows) or any(not isinstance(x,str) or not x.strip() for x in translations):raise _error()
            for row,chinese in zip(rows,translations):row['chinese']=chinese.strip()
            data={'version':VERSION,'source_sha256':fingerprint,'rows':rows,
                  'chinese_source':'Google 网页逐句机器翻译（非官方通路，需复核）'}
            _publish(store,'sentence-study.json',data)
        result.update(sentence_version=VERSION,sentence_count=len(data['rows']),bilingual_count=len(data['rows']),
                      bilingual_preview=data['rows'][:200],chinese_source=data['chinese_source'])
        if '逐句学习' not in result['warning']:result['warning']+=' 逐句学习补标点与译文需复核；句内时间为估算，视频截断内容会标为残句。'
        # A previously exported paragraph Word is still on disk, but is not the new sentence version.
        if result.get('word_sentence_version')!=VERSION:
            result['files'].pop('docx',None);result.pop('desktop_path',None)
        store.publish_metadata(result)
        return result


class SentencePreparation:
    def __init__(self,root):
        self.root=Path(root);self.lock=threading.Lock();self.jobs={};self.closed=False
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='sentence-study')

    def prepare(self,job_id):
        if not isinstance(job_id,str) or not re.fullmatch(r'[a-f0-9]{32}',job_id):raise ValueError('任务编号无效。')
        from .study_export import _Retained
        store=_Retained(self.root,job_id);_source(store,job_id)
        with self.lock:
            if self.closed:raise UserError('busy','工具正在关闭。')
            if self.jobs.get(job_id,{}).get('status') in ('queued','running'):return
            if sum(job['status'] in ('queued','running') for job in self.jobs.values())>=8:raise UserError('busy','逐句整理队列已满，请稍候。')
            self.jobs[job_id]={'id':job_id,'status':'queued','message':'正在准备逐句中英对照。'}
            self.executor.submit(self._run,job_id)

    def _run(self,job_id):
        def report(stage,message,**extra):
            with self.lock:self.jobs[job_id].update(status='running',stage=stage,message=message,**extra)
        try:
            result=prepare_sentences(self.root,job_id,report=report)
            with self.lock:self.jobs[job_id].update(status='done',message='逐句中英对照已完成。',result=result)
        except (UserError,ValueError) as error:
            with self.lock:self.jobs[job_id].update(status='error',message=str(error))
        except Exception:
            with self.lock:self.jobs[job_id].update(status='error',message='逐句整理失败，原字幕保留，请检查模型或网络后重试。')

    def snapshot(self,job_id):
        with self.lock:return dict(self.jobs.get(job_id,{'id':job_id,'status':'idle','message':'尚未按完整句子整理。'}))

    def active(self):
        with self.lock:return any(job['status'] in ('queued','running') for job in self.jobs.values())

    def close(self):
        with self.lock:self.closed=True
        self.executor.shutdown(wait=True)
