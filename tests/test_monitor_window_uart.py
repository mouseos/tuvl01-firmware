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
    def test_missing_start_reply_is_reported_and_recovers(self):
        t=Fake('unused');r={}
        def expect(line):
            if line=='MONWIN probe start':raise TimeoutError('start missing')
            return line
        with mock.patch.object(t,'expect',side_effect=expect), mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
            with self.assertRaisesRegex(TimeoutError,'start missing'):
                m.probe(t,pathlib.Path('unused'),r,timing=True)
        self.assertNotIn('probe_started',r)
        self.assertEqual(r['probe_error'],'start missing')
        self.assertTrue(r['uart_responding'])
        self.assertEqual(t.ready,2)
    def test_probe_error_is_retained_when_capture_also_fails(self):
        t=Fake(TimeoutError('probe timeout'));r={}
        with mock.patch.object(m,'capture',side_effect=RuntimeError('capture failure')):
            with self.assertRaisesRegex(RuntimeError,'capture failure'):
                m.probe(t,pathlib.Path('unused'),r)
        self.assertEqual(r['probe_error'],'probe timeout')
        self.assertEqual(r['capture_error'],'capture failure')
        self.assertTrue(r['uart_responding'])
    def test_state_snapshots_label_each_lifecycle_boundary(self):
        t=Fake('MONWIN probe end status=read-restored-unclassified-reinitialize-required')
        with mock.patch.object(m,'snapshot',side_effect=[{'61:97':x} for x in (12,76,116,204)]) as snap, mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
            r=m.probe(t,pathlib.Path('unused'),timing=True,snapshot_state=True)
        self.assertEqual(snap.call_count,4)
        self.assertEqual([r[key]['61:97'] for key in ('state_before_probe','state_after_probe','state_after_reload','state_after_capture')],[12,76,116,204])
    def test_post_probe_state_failure_still_reloads(self):
        t=Fake('MONWIN probe end status=read-restored-unclassified-reinitialize-required')
        with mock.patch.object(m,'snapshot',side_effect=[{},RuntimeError('state read'),{},{}]), mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
            with self.assertRaisesRegex(RuntimeError,'state read'):
                m.probe(t,pathlib.Path('unused'),snapshot_state=True)
        self.assertEqual(t.ready,2)
        self.assertEqual(t.sent[-1],b'i')
    def test_timing_opcode_and_timestamp_parser(self):
        t=Fake('MONWIN probe end status=read-restored-unclassified-reinitialize-required')
        with mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
            self.assertTrue(m.probe(t,pathlib.Path('unused'),timing=True)['timing'])
        self.assertEqual(t.sent[2],b'\x86')
        parsed=m.observations(b'MONWIN buffered phase=00000002 pause_ms=0000000a\nMONWIN time phase=00000002 index=00000000 before=00000010 after=00000020\nMONWIN time phase=00000002 index=RTOS tick\n')
        self.assertEqual(parsed['buffered'],[{'phase':2,'pause_ms':10}])
        self.assertEqual(parsed['times'],[{'phase':2,'index':0,'before':16,'after':32}])
    def test_capture_failure_still_checks_uart_and_preserves_error(self):
        t=Fake('MONWIN probe end status=read-restored-unclassified-reinitialize-required')
        report={}
        with mock.patch.object(m,'capture',side_effect=RuntimeError('capture failed')):
            with self.assertRaisesRegex(RuntimeError,'capture failed'):
                m.probe(t,pathlib.Path('unused'),report,updates=True)
        self.assertEqual(t.ready,2)
        self.assertEqual(report['capture_error'],'capture failed')
        self.assertTrue(report['uart_responding'])
        self.assertEqual(t.sent[-1],b'i')
    def test_update_probe_lifecycle(self):
        cases=['MONWIN probe end status=read-restored-unclassified-reinitialize-required',
               'MONWIN probe end status=read-failed-restored-reinitialize-required',TimeoutError('probe')]
        for result in cases:
            t=Fake(result)
            with mock.patch.object(m,'capture',return_value=(b'',{'frames':0})):
                if result==cases[0]:self.assertTrue(m.probe(t,pathlib.Path('unused'),updates=True)['updates'])
                else:
                    with self.assertRaises((RuntimeError,TimeoutError)):m.probe(t,pathlib.Path('unused'),updates=True)
            self.assertEqual(t.ready,2)
            self.assertEqual(t.sent,[bytes([16]),b'E',b'\x85',bytes([16]),b'E',b'i'])
    def test_block_metadata_identifies_reselection(self):
        raw=b'MONWIN block phase=00000009 requested=00000000 reselect=00000002\r\nMONWIN block phase=0000000d requested=00000004 reselect=RTOS tick\n'
        self.assertEqual(m.observations(raw)['blocks'],[{'phase':9,'requested':0,'reselect':2}])
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
