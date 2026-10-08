"""Clock wrap, failed requests, stop freeze and disjoint IO accounting."""
import ctypes as C,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Bin(C.Structure):
    _fields_=[(x,C.c_uint32) for x in ['calls','ticks','minimum','maximum','requested_bytes','failed','overflow']]
class Timing(C.Structure):
    _fields_=[('active',C.c_uint32),('start',C.c_uint32),('duration',C.c_uint32),('bin',Bin*7)]
class IO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)/'io.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/wifi_io_timing.c'),'-o',str(p)],check=True)
        cls.c=C.CDLL(str(p));cls.c.wifi_io_start.argtypes=[C.POINTER(Timing),C.c_uint32];cls.c.wifi_io_stop.argtypes=cls.c.wifi_io_start.argtypes
        cls.c.wifi_io_record.argtypes=[C.POINTER(Timing),C.c_uint,C.c_uint,C.c_uint32,C.c_uint32,C.c_int]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_disjoint_addresses_and_zero_tick_reads(self):
        for a,k in [(16,0),(32,1),(36,1),(80,2),(4,3),(0,3)]:self.assertEqual(self.c.wifi_io_read_kind(a),k)
        s=Timing();self.c.wifi_io_start(C.byref(s),10)
        for kind,begin,end in [(0,10,11),(1,11,13),(1,13,13),(2,13,14),(5,14,15)]:
            self.c.wifi_io_record(C.byref(s),kind,1536 if kind==5 else 4,begin,end,0)
        self.c.wifi_io_stop(C.byref(s),15);self.assertEqual(s.duration,5);self.assertEqual(sum(x.ticks for x in s.bin),5)
        self.assertEqual((s.bin[1].calls,s.bin[1].minimum,s.bin[1].maximum),(2,0,2));self.assertEqual(s.bin[5].requested_bytes,1536)
    def test_stop_freezes_uart_and_post_stream_operations(self):
        s=Timing();self.c.wifi_io_start(C.byref(s),1);self.c.wifi_io_record(C.byref(s),4,512,2,4,1);self.c.wifi_io_stop(C.byref(s),5)
        before=bytes(s);self.c.wifi_io_record(C.byref(s),0,4,5,999,0);self.c.wifi_io_stop(C.byref(s),999);self.assertEqual(bytes(s),before)
        self.assertEqual(s.bin[4].failed,1);self.assertEqual(s.bin[4].requested_bytes,512)
    def test_clock_wrap_and_reset_do_not_carry_previous_trial(self):
        s=Timing();self.c.wifi_io_start(C.byref(s),0xfffffffe);self.c.wifi_io_record(C.byref(s),0,4,0xffffffff,1,0);self.c.wifi_io_stop(C.byref(s),2)
        self.assertEqual((s.duration,s.bin[0].ticks),(4,2));self.c.wifi_io_start(C.byref(s),3)
        self.assertEqual((s.active,s.duration,s.bin[0].calls),(1,0,0));self.assertEqual(s.bin[0].minimum,0xffffffff)
    def test_saturation_flags_invalid_average_and_kind_rejection(self):
        s=Timing();self.c.wifi_io_start(C.byref(s),0);s.bin[0].calls=0xffffffff;s.bin[0].ticks=0xfffffffe;s.bin[0].requested_bytes=0xffffffff
        self.c.wifi_io_record(C.byref(s),0,4,1,10,0);self.assertEqual((s.bin[0].calls,s.bin[0].ticks,s.bin[0].requested_bytes),(0xffffffff,)*3);self.assertEqual(s.bin[0].overflow,1)
        before=bytes(s);self.c.wifi_io_record(C.byref(s),7,4,1,10,0);self.assertEqual(bytes(s),before)
if __name__=='__main__':unittest.main()
