"""Explicit single-word lookup, fixed HTTPS origin, no audio or caption upload."""
from collections import OrderedDict
import copy
import json
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class DictionaryError(Exception):pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise DictionaryError('词典服务发生重定向，已停止查询。')


def _text(value,maximum):
    return value[:maximum] if isinstance(value,str) else ''


def _link(value):
    if not isinstance(value,str) or len(value)>1000:return ''
    parsed=urlparse(value)
    return value if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password else ''


class DictionaryClient:
    def __init__(self,opener=None):
        self.opener=opener or build_opener(_NoRedirect()).open
        self.cache=OrderedDict();self.lock=threading.Lock();self.slots=threading.BoundedSemaphore(2)

    def lookup(self,word):
        if not isinstance(word,str) or not re.fullmatch(r"[A-Za-z][A-Za-z'-]{0,63}",word):
            raise ValueError('请选择单个英文词语（最多64个字符）。')
        word=word.lower()
        with self.lock:
            if word in self.cache:return copy.deepcopy(self.cache[word])
        if not self.slots.acquire(timeout=.5):raise DictionaryError('词典正在查询，请稍后再试。')
        try:
            address='https://api.dictionaryapi.dev/api/v2/entries/en/'+word
            request=Request(address,headers={'User-Agent':'SubtitleStudio-PublicBeta/0.1','Accept':'application/json'})
            with self.opener(request,timeout=12) as response:
                if hasattr(response,'geturl') and response.geturl()!=address:raise DictionaryError('词典来源发生变化，已停止查询。')
                raw=response.read(512*1024+1)
            if len(raw)>512*1024:raise DictionaryError('词典响应过大。')
            data=json.loads(raw)
            if not isinstance(data,list) or not data or not isinstance(data[0],dict):raise DictionaryError('未找到该词的释义。')
            entry=data[0];definitions=[]
            for meaning in entry.get('meanings',[])[:8]:
                if not isinstance(meaning,dict):continue
                for definition in meaning.get('definitions',[])[:3]:
                    if isinstance(definition,dict) and isinstance(definition.get('definition'),str):
                        definitions.append({'part_of_speech':_text(meaning.get('partOfSpeech'),50),'definition':_text(definition['definition'],1000),'example':_text(definition.get('example'),1000)})
                    if len(definitions)>=3:break
                if len(definitions)>=3:break
            if not definitions:raise DictionaryError('未找到该词的释义。')
            phonetic=_text(entry.get('phonetic'),200)
            if not phonetic:
                for value in entry.get('phonetics',[])[:8]:
                    if isinstance(value,dict) and isinstance(value.get('text'),str):phonetic=value['text'][:200];break
            sources=entry.get('sourceUrls',[])
            source=next((_link(value) for value in sources[:8] if _link(value)),'https://dictionaryapi.dev/') if isinstance(sources,list) else 'https://dictionaryapi.dev/'
            license=entry.get('license') if isinstance(entry.get('license'),dict) else {}
            result={'word':word,'phonetic':phonetic,'definitions':definitions,'source_url':source,'license':{'name':_text(license.get('name'),100),'url':_link(license.get('url'))}}
            with self.lock:
                self.cache[word]=result
                if len(self.cache)>256:self.cache.popitem(last=False)
            return copy.deepcopy(result)
        except HTTPError as error:
            raise DictionaryError('未找到该词；请尝试词典原形。' if error.code==404 else '词典暂时不可用，请稍后重试。') from None
        except (URLError,OSError,ValueError,TypeError,KeyError):
            raise DictionaryError('词典查询失败，请检查网络或稍后重试。') from None
        finally:self.slots.release()
