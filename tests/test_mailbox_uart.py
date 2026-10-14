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
    def test_reload_on_success_failure_and_timeout(self):
        cases=['MAILBOX probe end status=read-restored-unclassified-reinitialize-required',
               'MAILBOX probe end status=restore-failed-reinitialize-required',TimeoutError('probe')]
        for result in cases:
            with self.subTest(result=result):
                t=Fake(result)
                with mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
                    if result==cases[0]:self.assertTrue(m.probe(t,pathlib.Path('unused'))['uart_responding'])
                    else:
                        with self.assertRaises((RuntimeError,TimeoutError)):m.probe(t,pathlib.Path('unused'))
                self.assertEqual(t.ready,2)
                self.assertEqual(t.sent,[bytes([16]),b'E',b'\x81',bytes([16]),b'E',b'i'])
if __name__=='__main__':unittest.main()
