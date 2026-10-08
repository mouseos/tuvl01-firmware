"""Disjoint loop phases, TS-only classes, partial stop and counter wrap."""
import ctypes as C,pathlib,subprocess,tempfile,unittest
from test_wifi_io_timing import Bin,Timing
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Service(C.Structure):
    _fields_=[('phases',Timing),('loops',Timing)]+[(x,C.c_uint32) for x in ['last','stage','open','loop_begin','stalls_begin','tx_begin','stalled','sent','invalid']]
class Loops(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)/'service.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/wifi_service_timing.c'),str(ROOT/'src/wifi_io_timing.c'),'-o',str(p)],check=True)
        cls.c=C.CDLL(str(p));cls.c.wifi_service_start.argtypes=[C.POINTER(Service),C.c_uint32];cls.c.wifi_service_stop.argtypes=cls.c.wifi_service_start.argtypes
        cls.c.wifi_service_mark.argtypes=[C.POINTER(Service),C.c_uint,C.c_uint32,C.c_uint32,C.c_uint32]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def mark(self,s,m,t,stalls=100,tx=10):self.c.wifi_service_mark(C.byref(s),m,t,stalls,tx)
    def test_five_phases_and_all_four_classes(self):
        for stalls,sent,kind in [(1,0,0),(0,1,1),(1,2,2),(0,0,3)]:
            s=Service();self.c.wifi_service_start(C.byref(s),0)
            self.mark(s,1,10);self.mark(s,2,20)
            self.mark(s,3,35,100+stalls,10+sent);self.mark(s,4,40);self.mark(s,5,50)
            self.c.wifi_service_stop(C.byref(s),50)
            self.assertEqual([b.ticks for b in s.phases.bin[:5]],[10,10,15,5,10]);self.assertEqual(s.invalid,0)
            self.assertEqual((s.loops.bin[kind].calls,s.loops.bin[kind].ticks,s.loops.bin[kind].requested_bytes),(1,50,sent))
            self.assertEqual(sum(b.calls for b in s.loops.bin),1)
    def test_stop_in_phase_counts_partial_but_not_completed_loop(self):
        s=Service();self.c.wifi_service_start(C.byref(s),10);self.mark(s,1,20);self.mark(s,2,25)
        self.c.wifi_service_stop(C.byref(s),30)
        self.assertEqual([b.ticks for b in s.phases.bin[:5]],[10,5,5,0,0]);self.assertEqual(s.phases.duration,20)
        self.assertEqual(sum(b.calls for b in s.loops.bin),0)
        before=bytes(s);self.mark(s,3,999);self.c.wifi_service_stop(C.byref(s),999);self.assertEqual(bytes(s),before)
    def test_timestamp_and_event_counter_wrap(self):
        s=Service();self.c.wifi_service_start(C.byref(s),0xfffffff0)
        self.mark(s,1,0xfffffff5);self.mark(s,2,0xfffffffe,0xffffffff,0xfffffffe)
        self.mark(s,3,3,0,1);self.mark(s,4,6);self.mark(s,5,0x20)
        self.assertEqual(s.loops.bin[2].requested_bytes,3);self.assertEqual(s.loops.bin[2].ticks,48)
        self.assertEqual(sum(b.ticks for b in s.phases.bin),48)
    def test_gaps_saturation_and_invalid_sequence_are_visible(self):
        s=Service();self.c.wifi_service_start(C.byref(s),0)
        for m in range(1,6):self.mark(s,m,m*10)
        self.mark(s,0,60);self.mark(s,1,70);self.c.wifi_service_stop(C.byref(s),80)
        self.assertEqual(sum(b.ticks for b in s.phases.bin),70);self.assertEqual(s.phases.duration,80)
        self.c.wifi_service_start(C.byref(s),0);self.mark(s,3,1);self.assertEqual(s.invalid,1)
        self.c.wifi_service_start(C.byref(s),0);s.loops.bin[3].calls=0xffffffff
        for m in range(1,6):self.mark(s,m,m*10)
        self.assertEqual(s.loops.bin[3].overflow,1)
if __name__=='__main__':unittest.main()
