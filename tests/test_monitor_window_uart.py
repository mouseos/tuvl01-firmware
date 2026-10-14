"""Full normal reload after success, failed probe, or timeout; complete rows."""
import sys,pathlib,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import tuner_monitor_window_probe as m

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

class MonitorWindowUART(unittest.TestCase):
    def test_reload_on_success_failure_and_timeout(self):
        cases=['MONWIN probe end status=read-restored-unclassified-reinitialize-required',
               'MONWIN probe end status=restore-failed-reinitialize-required',TimeoutError('probe')]
        for result in cases:
            with self.subTest(result=result):
                t=Fake(result)
                with mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
                    if result==cases[0]:self.assertTrue(m.probe(t,pathlib.Path('unused'))['uart_responding'])
                    else:
                        with self.assertRaises((RuntimeError,TimeoutError)):m.probe(t,pathlib.Path('unused'))
                self.assertEqual(t.ready,2)
                self.assertEqual(t.sent,[bytes([16]),b'E',b'\x83',bytes([16]),b'E',b'i'])
    def test_partial_rows_not_inferred(self):
        raw=b'MONWIN sample phase=00000001 index=00000000 selector=00000000 ba=00000012 bb=00000034\r\nMONWIN sample phase=00000002 index=00000000 selector=RTOS tick ba=00000056 bb=00000078\n'
        self.assertEqual(m.observations(raw)['rows'],[{'phase':1,'index':0,'selector':0,'ba':0x12,'bb':0x34}])
if __name__=='__main__':unittest.main()
