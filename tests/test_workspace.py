import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from beda.workspace import Handler
from beda.storage import Database
from beda.live import LiveService
from tests.test_live import FakeModel

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.write_lock=threading.Lock()
        self.server.db=Database(str(Path(self.tmp.name)/'test.db'));self.server.db.initialize()
        self.server.service=LiveService(self.server.db,FakeModel())
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def post(self,path,data,origin):
        request=Request(self.url+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':origin,'X-BEDA-Workspace':'1'})
        with urlopen(request) as response:return json.load(response)
    def test_cross_origin_rejected_and_same_origin_review_persists(self):
        payload={'id':'custom','body':'Call 0400 123 456 for solar'}
        with self.assertRaises(HTTPError) as error:self.post('/api/process',payload,'https://untrusted.test')
        self.assertEqual(error.exception.code,403)
        error.exception.close()
        self.assertEqual(self.post('/api/process',payload,self.url)['status'],'PENDING_APPROVAL')
        self.post('/api/decide',{'id':'custom','approve':True,'version':1},self.url)
        action=self.server.db.list_actions_for_enquiry('custom')[0]
        self.assertEqual(action.status,'SUCCEEDED')
        self.assertFalse(action.result['external_message_sent'])
        with self.assertRaises(HTTPError) as error:self.post('/api/decide',{'id':'custom','approve':True,'version':1},self.url)
        error.exception.close()

    def test_progress_readable_during_model_call_and_second_write_rejected(self):
        from concurrent.futures import ThreadPoolExecutor
        entered,release=threading.Event(),threading.Event()
        original=self.server.service.model.generate
        def slow(*args):
            entered.set()
            if not release.wait(5):raise RuntimeError('Test synchronization failed')
            return original(*args)
        self.server.service.model.generate=slow
        with ThreadPoolExecutor() as pool:
            pending=pool.submit(self.post,'/api/process',{'id':'stream','body':'Call 0400 123 456'},self.url)
            try:
                self.assertTrue(entered.wait(3))
                with urlopen(self.url+'/api/run/stream',timeout=2) as response:
                    progress=json.load(response)
                self.assertIn('STAGE_STARTED',[e['event_type'] for e in progress['audit']])
                self.assertNotIn('APPROVAL_REQUESTED',[e['event_type'] for e in progress['audit']])
                with self.assertRaises(HTTPError) as error:
                    self.post('/api/process',{'id':'other'},self.url)
                self.assertEqual(error.exception.code,409);error.exception.close()
            finally:
                release.set()
            self.assertEqual(pending.result()['status'],'PENDING_APPROVAL')

    def test_history_endpoint_and_stale_browser_approval(self):
        self.post('/api/process',{'id':'history','body':'Call 0400 123 456'},self.url)
        self.post('/api/rerun',{'id':'history','mode':'draft','request_id':'browser-rerun-001'},self.url)
        with urlopen(self.url+'/api/run/history?version=1') as response:
            old=json.load(response)
        self.assertEqual(old['version'],1)
        self.assertEqual(old['current_version'],2)
        self.assertTrue(all(e['details']['run_version']==1 for e in old['audit']))
        self.assertEqual(old['actions'][0]['status'],'SUPERSEDED')
        with self.assertRaises(HTTPError) as error:
            self.post('/api/decide',{'id':'history','approve':True,'version':1},self.url)
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(self.url+'/api/run/history') as response:
            current=json.load(response)
        self.assertEqual(current['version'],2)
        self.assertEqual(current['enquiry']['status'],'PENDING_APPROVAL')

    def test_document_page_api_and_reviewed_update(self):
        with urlopen(self.url+'/documents') as response:
            self.assertIn(b'Document history',response.read())
        with urlopen(self.url+'/api/documents') as response:
            documents=json.load(response)['documents']
        self.assertEqual(len(documents),3)
        document=documents[0]
        result=self.post('/api/documents/save',{'filename':document['filename'],'content':document['current']['content']+'\nDemo note.',
            'note':'Review note added','revision':1},self.url)
        self.assertEqual(result['document']['current']['revision'],2)
        with self.assertRaises(HTTPError) as error:
            self.post('/api/documents/save',{'filename':document['filename'],'content':'Changed','note':'test','revision':2},'https://other.test')
        self.assertEqual(error.exception.code,403);error.exception.close()

    def test_junk_restore_endpoint_rejects_cross_origin_and_stale_version(self):
        from tests.test_junk import JunkModel
        self.server.service=LiveService(self.server.db,JunkModel())
        result=self.post('/api/process',{'id':'api-junk','body':'Buy bulk leads'},self.url)
        self.assertEqual(result['status'],'JUNK')
        for origin,version,code in [('https://other.test',1,403),(self.url,99,400),(self.url,None,400)]:
            with self.assertRaises(HTTPError) as error:
                self.post('/api/junk/restore',{'id':'api-junk','version':version},origin)
            self.assertEqual(error.exception.code,code);error.exception.close()
        result=self.post('/api/junk/restore',{'id':'api-junk','version':1},self.url)
        self.assertEqual(result['status'],'PENDING_APPROVAL')
        self.assertEqual(self.server.service.runs.current('api-junk'),2)
        with self.assertRaises(HTTPError) as error:
            self.post('/api/junk/restore',{'id':'api-junk','version':1},self.url)
        self.assertEqual(error.exception.code,400);error.exception.close()
