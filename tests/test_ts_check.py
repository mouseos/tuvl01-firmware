import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class State(ctypes.Structure):
    _fields_=[(n,ctypes.c_uint32) for n in ('packets','sync','tei','adaptation','comparisons','cc_jumps','cc_repeats')]+[('last',ctypes.c_uint8*8192)]
class Check(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)/'check.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/ts_check.c'),'-o',str(p)],check=True)
        cls.lib=ctypes.CDLL(str(p));cls.lib.ts_check_reset.argtypes=[ctypes.POINTER(State)]
        cls.lib.ts_check_packet.argtypes=[ctypes.POINTER(State),ctypes.c_void_p]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def state(self):
        s=State();self.lib.ts_check_reset(ctypes.byref(s));return s
    def packet(self,pid=100,cc=0,afc=1,length=0,discontinuity=False,tei=False):
        p=bytearray([0xff]*188);p[:6]=bytes([0x47,(pid>>8)|(128 if tei else 0),pid&255,(afc<<4)|cc,length,128 if discontinuity else 0]);return p
    def feed(self,s,p):self.lib.ts_check_packet(ctypes.byref(s),bytes(p))
    def test_wrap_jump_and_repeat_are_distinct(self):
        s=self.state()
        for cc in (14,15,0,4,4,5):self.feed(s,self.packet(cc=cc))
        self.assertEqual((s.packets,s.comparisons,s.cc_jumps,s.cc_repeats),(6,5,1,1))
    def test_pid_isolation_null_and_adaptation_only(self):
        s=self.state()
        for p in (self.packet(100,0),self.packet(200,4),self.packet(100,0,2,183),self.packet(8191,5),self.packet(8191,8),self.packet(100,1)):
            self.feed(s,p)
        self.assertEqual((s.comparisons,s.cc_jumps,s.cc_repeats),(1,0,0))
    def test_discontinuity_resets_comparison(self):
        s=self.state();self.feed(s,self.packet(cc=0));self.feed(s,self.packet(cc=8,afc=3,length=1,discontinuity=True));self.feed(s,self.packet(cc=9))
        self.assertEqual((s.comparisons,s.cc_jumps),(1,0))
    def test_bad_headers_and_tei_are_counted(self):
        s=self.state();p=self.packet();p[0]=0;self.feed(s,p)
        for p in (self.packet(afc=0),self.packet(afc=2,length=184),self.packet(afc=3,length=183),self.packet(tei=True)):
            self.feed(s,p)
        self.assertEqual((s.packets,s.sync,s.adaptation,s.tei,s.comparisons),(5,1,3,1,0))
    def test_reset_clears_all_pid_history(self):
        s=self.state();self.feed(s,self.packet(cc=8));self.lib.ts_check_reset(ctypes.byref(s));self.feed(s,self.packet(cc=3))
        self.assertEqual((s.packets,s.comparisons,s.cc_jumps),(1,0,0))
