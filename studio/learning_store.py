"""Per-user local learning state. Never accepts filesystem paths from clients."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import threading

from .subtitles import normalize_youtube_url


def _text(value,limit,empty=True):
    if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()) or any(ord(c)<32 and c not in '\n\t' for c in value):
        raise ValueError('学习记录内容无效或过长。')
    return value


def _time(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=604800:
        raise ValueError('学习进度无效。')
    return float(value)


class LearningStore:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'learning.sqlite3';self.lock=threading.RLock()
        if self.path.is_symlink() or self.root.is_symlink() or self.root.is_junction():
            raise ValueError('学习目录不能是符号链接。')
        with self._db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS terms (
                key TEXT PRIMARY KEY,state TEXT NOT NULL,term TEXT NOT NULL,
                english TEXT NOT NULL,chinese TEXT NOT NULL,url TEXT NOT NULL,
                start REAL NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS progress (job_id TEXT PRIMARY KEY,time REAL NOT NULL);''')

    @contextmanager
    def _db(self):
        with self.lock:
            db=sqlite3.connect(self.path,timeout=5)
            db.row_factory=sqlite3.Row
            try:
                yield db;db.commit()
            finally:db.close()

    def profile(self):
        with self._db() as db:
            rows=db.execute('SELECT * FROM terms ORDER BY created_at DESC,key').fetchall()
            progress=dict(db.execute('SELECT job_id,time FROM progress').fetchall())
        saved=[{k:row[k] for k in ('key','term','english','chinese','url','start','created_at')} for row in rows if row['state']=='learn']
        return {'known':sorted(row['key'] for row in rows if row['state']=='known'),'saved':saved,'progress':progress}

    def set_term(self,data):
        if not isinstance(data,dict) or set(data)-{'key','term','state','english','chinese','url','start'}:
            raise ValueError('学习记录参数无效。')
        key=data.get('key');state=data.get('state');term=_text(data.get('term',''),200,False)
        if not isinstance(key,str) or not re.fullmatch(r'[a-z0-9][a-z0-9 -]{0,119}',key) or state not in ('known','learn','neutral'):
            raise ValueError('请选择有效词语与学习状态。')
        english=_text(data.get('english',''),4000);chinese=_text(data.get('chinese',''),4000)
        url=data.get('url') or ''
        if url:
            if not isinstance(url,str):raise ValueError('来源链接无效。')
            url=normalize_youtube_url(url)
        start=_time(data.get('start',0))
        with self._db() as db:
            if state=='neutral':db.execute('DELETE FROM terms WHERE key=?',(key,))
            else:
                if not db.execute('SELECT 1 FROM terms WHERE key=?',(key,)).fetchone() and db.execute('SELECT COUNT(*) FROM terms').fetchone()[0]>=5000:
                    raise ValueError('学习词库已达5000条，请先移除部分记录。')
                db.execute('INSERT OR REPLACE INTO terms VALUES (?,?,?,?,?,?,?,?)',
                           (key,state,term,english,chinese,url,start,datetime.now(timezone.utc).isoformat()))
        return self.profile()

    def _metadata(self,identity):
        if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):return None
        folder=self.root/'results'/identity;path=folder/'metadata.json'
        try:
            if any(p.is_symlink() or p.is_junction() for p in (self.root/'results',folder,path)) or not path.is_file() or path.stat().st_size>2*1024*1024:return None
            data=json.loads(path.read_text('utf-8'))
            return data if isinstance(data,dict) and data.get('id')==identity else None
        except (OSError,ValueError,UnicodeError):return None

    def set_progress(self,identity,value):
        value=_time(value)
        if self._metadata(identity) is None:raise ValueError('没有对应的本机学习任务。')
        with self._db() as db:
            db.execute('INSERT OR REPLACE INTO progress VALUES (?,?)',(identity,value))

    def history(self):
        results=self.root/'results'
        if not results.is_dir() or results.is_symlink() or results.is_junction():return []
        progress=self.profile()['progress'];items=[]
        for directory in list(results.iterdir())[:1000]:
            data=self._metadata(directory.name)
            if data is None:continue
            try:
                title=_text(data.get('title',''),500,False)
                url=data.get('url') or None
                if url:url=normalize_youtube_url(url)
                count=data.get('sentence_count',data.get('bilingual_count',data.get('count',0)))
                if type(count) is not int or not 0<=count<=1000000:continue
                created=_text(data.get('created_at',''),100)
            except (TypeError,ValueError):continue
            items.append({'id':directory.name,'title':title,'url':url,'cue_count':count,'created_at':created,'position':progress.get(directory.name,0)})
        return sorted(items,key=lambda item:(item['created_at'],item['id']),reverse=True)
