import sys,pathlib,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import tuner_d4_window_probe as m

class UART:
    def __init__(self):self.sent=[]
    def write(self,data):self.sent.append(data)
    def expect(self,line):return line

class D4Window(unittest.TestCase):
    def run_probe(self,fail=False,restore_fail=False):
        state={'d4':0xde,'reads':0,'writes':[]};t=UART();r={}
        def reg(t,bank,addr,value=None):
            self.assertEqual(bank,0x61);self.assertIn(addr,(0xd4,0xd5))
            if value is not None:
                state['writes'].append(value);state['d4']=value
                if restore_fail and len(state['writes'])==4:raise RuntimeError('restore uncertain')
            if addr==0xd5:
                state['reads']+=1
                if fail and state['reads']==2:raise RuntimeError('sample failed')
                return 0x3f
            return state['d4']
        with mock.patch.object(m,'register',side_effect=reg), mock.patch.object(m,'normal',return_value='SERVE end status=ready') as normal, mock.patch.object(m,'snapshot',return_value={}), mock.patch.object(m,'capture',return_value=(b'',{})):
            if fail:
                with self.assertRaisesRegex(RuntimeError,'sample failed'):m.probe(t,pathlib.Path('unused'),r)
            else:m.probe(t,pathlib.Path('unused'),r)
            self.assertEqual(normal.call_count,2)
        self.assertTrue(r['uart_responding']);self.assertEqual(state['writes'][-1],0xde)
        return state,r
    def test_known_fields_preserve_other_bits_and_restore(self):
        state,r=self.run_probe()
        self.assertEqual(state['writes'],[0xd6,0xde,0xe6,0xde])
        self.assertEqual(len(r['rows']),48)
        self.assertFalse(r['iq_identified'])
    def test_failure_restores_and_reloads(self):
        state,r=self.run_probe(fail=True)
        self.assertEqual(r['probe_error'],'sample failed');self.assertTrue(r['d4_restored'])
    def test_uncertain_restore_still_reloads(self):
        state,r=self.run_probe(restore_fail=True)
        self.assertEqual(r['restore_error'],'restore uncertain')
        self.assertNotIn('d4_restored',r)

if __name__=='__main__':unittest.main()
