import json
from pathlib import Path
import tempfile
import threading
import unittest
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from studio.server import make_server, parse_byte_range


class FakeStore:
    busy = False
    def __init__(self, path): self.path=path;self.prepared=0
    def load_study(self, job):
        return {'id':job,'title':'Example','url':'https://youtu.be/BaW_jenozKc',
                'cues':[{'start':i,'end':i+1,'english':str(i),'chinese':''} for i in range(251)]}
    def snapshot(self, job): return {'status':'ready','message':'原音已准备好'}
    def prepare(self, job): self.prepared+=1;return self.snapshot(job)
    def media_file(self, job): return self.path
    def close(self): pass


class RangeTests(unittest.TestCase):
    def test_valid_single_ranges(self):
        self.assertEqual(parse_byte_range(None,10),(0,9,False))
        self.assertEqual(parse_byte_range('bytes=2-5',10),(2,5,True))
        self.assertEqual(parse_byte_range('bytes=7-',10),(7,9,True))
        self.assertEqual(parse_byte_range('bytes=-3',10),(7,9,True))
        self.assertEqual(parse_byte_range('bytes=0-999',10),(0,9,True))
    def test_invalid_or_multiple_ranges_rejected(self):
        for value in ('bytes=20-','bytes=-0','bytes=8-2','items=0-1','bytes=0-1,3-4','bytes='):
            with self.subTest(value=value), self.assertRaises(ValueError):parse_byte_range(value,10)


class ShadowHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.job='b'*32;directory=self.root/'results'/self.job;directory.mkdir(parents=True)
        self.path=directory/'original-audio.wav';self.path.write_bytes(b'0123456789')
        self.store=FakeStore(self.path)
        self.server=make_server(self.root,0,shadowing=self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,body=None,headers=None,auth=True,method=None):
        h={'X-App-Token':self.server.token} if auth else {}
        h.update(headers or {})
        if body is not None:body=json.dumps(body).encode();h['Content-Type']='application/json'
        return urlopen(Request(self.base+path,data=body,headers=h,method=method),timeout=5)
    def media_url(self):
        with self.request(f'/api/jobs/{self.job}/audio') as r:return json.load(r)['media_url']
    def test_full_study_and_explicit_preparation(self):
        with self.request(f'/api/jobs/{self.job}/study') as r:self.assertEqual(len(json.load(r)['cues']),251)
        self.assertEqual(self.store.prepared,0)
        with self.request(f'/api/jobs/{self.job}/audio',{}) as r:self.assertEqual(json.load(r)['status'],'ready')
        self.assertEqual(self.store.prepared,1)
        with self.assertRaises(HTTPError) as e:self.request(f'/api/jobs/{self.job}/audio',{'url':'https://evil.example'})
        self.assertEqual(e.exception.code,400)
    def test_session_guard_and_per_job_ticket_are_required(self):
        with self.assertRaises(HTTPError) as e:self.request(f'/api/jobs/{self.job}/study',auth=False)
        self.assertEqual(e.exception.code,403)
        with self.assertRaises(HTTPError) as e:self.request(f'/media/{self.job}/audio?ticket=wrong',auth=False)
        self.assertEqual(e.exception.code,403)
        media=self.media_url()
        with self.assertRaises(HTTPError) as e:self.request(media,auth=False,headers={'Sec-Fetch-Site':'cross-site'})
        self.assertEqual(e.exception.code,403)
        other=media.replace(self.job,'c'*32)
        with self.assertRaises(HTTPError) as e:self.request(other,auth=False)
        self.assertEqual(e.exception.code,403)
    def test_native_audio_supports_ranges_and_head_without_session_in_url(self):
        media=self.media_url();self.assertNotIn(self.server.token,media)
        with self.request(media,headers={'Range':'bytes=2-5'},auth=False) as r:
            self.assertEqual(r.status,206);self.assertEqual(r.read(),b'2345')
            self.assertEqual(r.headers['Content-Range'],'bytes 2-5/10');self.assertEqual(r.headers['Accept-Ranges'],'bytes')
            self.assertEqual(r.headers['Content-Length'],'4')
        with self.request(media,auth=False,method='HEAD') as r:
            self.assertEqual(r.status,200);self.assertEqual(r.read(),b'');self.assertEqual(r.headers['Content-Length'],'10')
        with self.assertRaises(HTTPError) as e:self.request(media,headers={'Range':'bytes=50-'},auth=False)
        self.assertEqual(e.exception.code,416);self.assertEqual(e.exception.headers['Content-Range'],'bytes */10')
    def test_busy_audio_prevents_shutdown(self):
        self.store.busy=True
        with self.assertRaises(HTTPError) as e:self.request('/api/shutdown',{})
        self.assertEqual(e.exception.code,400)

    def test_media_tickets_expire_and_authenticated_status_can_renew(self):
        old=self.media_url()
        future=time.monotonic()+24*3600
        with patch('studio.server.time.monotonic',return_value=future):
            with self.assertRaises(HTTPError) as e:self.request(old,auth=False,method='HEAD')
            self.assertEqual(e.exception.code,403)
            new=self.media_url();self.assertNotEqual(old,new)
            with self.request(new,auth=False,method='HEAD') as r:self.assertEqual(r.status,200)
