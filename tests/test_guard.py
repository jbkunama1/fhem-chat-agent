import tempfile, time, unittest
from guard import Store, readonly

class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name+'/test.db')
    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()
    def test_read_allowlist(self):
        self.assertTrue(readonly('fhem_get_readings'))
        for name in ['fhem_set','fhem_command','fhem_web_command','fhem_delete','unknown','fhem_get_new']:
            self.assertFalse(readonly(name))
    def test_single_use_and_immutable_payload(self):
        action={'name':'fhem_set','args':{'device':'Lamp','value':'on'}}
        p=self.store.propose('web:daniel',action,120)
        action['args']['value']='off'
        payload,state=self.store.claim('web:daniel',p['id'],True)
        self.assertEqual(payload['args']['value'],'on')
        self.assertEqual(state,'consumed')
        with self.assertRaises(ValueError): self.store.claim('web:daniel',p['id'],True)
    def test_wrong_owner(self):
        p=self.store.propose('tg:1',{'name':'fhem_delete'},120)
        with self.assertRaises(ValueError): self.store.claim('tg:2',p['id'],True)
        self.assertIsNotNone(self.store.pending('tg:1'))
    def test_expired(self):
        p=self.store.propose('a',{},-1)
        self.assertEqual(self.store.claim('a',p['id'],True)[1],'expired')
    def test_rejected(self):
        p=self.store.propose('a',{},120)
        self.assertEqual(self.store.claim('a',p['id'],False)[1],'rejected')
    def test_restart_resolves_incomplete_tool_call(self):
        self.store.save('a',[{'role':'assistant','tool_calls':[{'id':'test-call'}]}])
        other=Store(self.tmp.name+'/test.db')
        self.assertEqual(other.load('a')[-1]['tool_call_id'],'test-call')
        self.assertEqual(other.load('a')[-1]['role'],'tool')
        other.db.close()
    def test_restart_cancels(self):
        p=self.store.propose('a',{},120)
        other=Store(self.tmp.name+'/test.db')
        with self.assertRaises(ValueError): other.claim('a',p['id'],True)
        other.db.close()

if __name__=='__main__': unittest.main()
