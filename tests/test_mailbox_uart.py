"""Ensure full chip patch reload follows successful/failed/timed-out probes."""
import sys,pathlib,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import tuner_mailbox_probe as m

class Fake:
    def __init__(self,result):self.result=result;self.sent=[];self.ready=0
    def write(self,b):self.sent.append(b)
    def expect(self,s):return s
    def wait(self,predicate,timeout):
        if self.sent[-1]==bytes([16]):self.ready+=1;s='SERVE end status=ready'
        elif self.sent[-1]==b'E':s='TS stream end status=stopped'
        else:
            if isinstance(self.result,Exception):raise self.result
            s=self.result
        assert predicate(s);return s

class MailboxUART(unittest.TestCase):
    def test_selected_operand_lifecycle_and_rejection(self):
        cases=['MAILBOX probe end status=read-restored-unclassified-reinitialize-required',
               'MAILBOX probe end status=read-failed-restored-reinitialize-required',TimeoutError('probe')]
        for result in cases:
            t=Fake(result)
            with mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
                if result==cases[0]:m.probe(t,pathlib.Path('unused'),operand=0x0f07)
                else:
                    with self.assertRaises((RuntimeError,TimeoutError)):m.probe(t,pathlib.Path('unused'),operand=0x0f07)
            self.assertEqual(t.ready,2)
            self.assertEqual(t.sent,[bytes([16]),b'E',bytes([0x84,2]),bytes([16]),b'E',b'i'])
        t=Fake(cases[0])
        with self.assertRaises(ValueError):m.probe(t,pathlib.Path('unused'),operand=0x1234)
        with self.assertRaises(ValueError):m.probe(t,pathlib.Path('unused'),known_operands=True,operand=0x0f07)
        self.assertEqual(t.sent,[])
    def test_complete_rows_and_operand_identity(self):
        raw=b'''MAILBOX probe start address=00000298 count=00000518 operand=00001ff0
MAILBOX transfer operand=00001ff0
MAILBOX transfer parity index=00000000 f8=00000050 expected=00000001
MAILBOX sample phase=00000001 index=00000000 sub6d=00000007 main6d=000000ab
MAILBOX sample phase=00000001 index=00000001 sub6d=RTOS tick main6d=000000cd
MAILBOX probe end status=read-restored-unclassified-reinitialize-required
MAILBOX probe start address=00000298 count=00000518 operand=00000f05
'''
        items=m.observations(raw)['items']
        self.assertEqual([x['operand'] for x in items],[0x1ff0,0xf05])
        self.assertEqual(items[0]['samples'],[{'phase':1,'index':0,'sub6d':7,'main6d':0xab}])
        self.assertEqual(items[0]['transfers'][0]['parity'],[{'index':0,'f8':0x50,'expected':1}])
        self.assertEqual(items[1]['samples'],[])
    def test_reload_on_success_failure_and_timeout(self):
        cases=['MAILBOX probe end status=read-restored-unclassified-reinitialize-required',
               'MAILBOX probe end status=restore-failed-reinitialize-required',TimeoutError('probe')]
        for known in [False,True]:
          for original in cases:
            result=original.replace('MAILBOX probe','MAILBOX sweep') if known and isinstance(original,str) else original
            with self.subTest(result=result,known=known):
                t=Fake(result)
                with mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
                    if original==cases[0]:self.assertTrue(m.probe(t,pathlib.Path('unused'),known_operands=known)['uart_responding'])
                    else:
                        with self.assertRaises((RuntimeError,TimeoutError)):m.probe(t,pathlib.Path('unused'),known_operands=known)
                self.assertEqual(t.ready,2)
                self.assertEqual(t.sent,[bytes([16]),b'E',b'\x82' if known else b'\x81',bytes([16]),b'E',b'i'])
if __name__=='__main__':unittest.main()
