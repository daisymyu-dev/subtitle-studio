import io
import json
import unittest
from urllib.error import HTTPError

from studio.dictionary import DictionaryClient, DictionaryError


class DictionaryTests(unittest.TestCase):
    def test_lookup_is_fixed_origin_bounded_and_preserves_attribution(self):
        calls=[]
        def opener(request,timeout):
            calls.append(request.full_url)
            return io.BytesIO(json.dumps([{'word':'example','phonetic':'/example/','audio':'https://untrusted.test/x','meanings':[{'partOfSpeech':'noun','definitions':[{'definition':'A self-authored definition.','example':'A self-authored sentence.'}]}],'sourceUrls':['https://en.wiktionary.org/wiki/example'],'license':{'name':'CC BY-SA','url':'https://creativecommons.org/licenses/by-sa/3.0/'}}]).encode())
        result=DictionaryClient(opener=opener).lookup('Example')
        self.assertEqual(calls,['https://api.dictionaryapi.dev/api/v2/entries/en/example'])
        self.assertEqual(result['definitions'][0]['definition'],'A self-authored definition.')
        self.assertEqual(result['license']['name'],'CC BY-SA');self.assertNotIn('audio',result)

    def test_invalid_words_never_make_requests(self):
        def opener(*args,**kwargs):self.fail('network request for invalid input')
        client=DictionaryClient(opener=opener)
        for word in ('https://other.test','../private','two words','a'*65,123,'x\nword','中文'):
            with self.subTest(word=word),self.assertRaises(ValueError):client.lookup(word)

    def test_http_failure_and_malformed_response_are_honest(self):
        def absent(*args,**kwargs):raise HTTPError('fixed',404,'not found',{},None)
        with self.assertRaises(DictionaryError):DictionaryClient(opener=absent).lookup('example')
        with self.assertRaises(DictionaryError):DictionaryClient(opener=lambda *a,**k:io.BytesIO(b'[]')).lookup('example')

    def test_redirect_to_other_origin_is_rejected(self):
        class Redirected(io.BytesIO):
            def geturl(self):return 'http://127.0.0.1/private'
        with self.assertRaises(DictionaryError):DictionaryClient(opener=lambda *a,**k:Redirected(b'[]')).lookup('example')
