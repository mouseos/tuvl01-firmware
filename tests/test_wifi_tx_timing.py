"""Run the actual timing bookkeeping, including contaminated and late events."""
import ctypes as C
import pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Bin(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('credits','credit_sum','credit_min','credit_max','writes','write_sum','done','done_sum','done_min','done_max','done_failed','poll_sum','poll_min','poll_max','poll_gap_max')]
class State(C.Structure):
    _fields_=[('bin',Bin*7)]+[(n,C.c_uint32) for n in ('active','packets','start','excluded','polls','last_poll','poll_gap')]+[('sample_packets',C.c_uint8*128),('sample_start',C.c_uint32*128)]
class Timing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)/'timing.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/wifi_tx_timing.c'),'-o',str(p)],check=True)
        cls.lib=C.CDLL(str(p))
        for name,args in {'reset':[],'other':[],'begin':[C.c_uint,C.c_uint32],'written':[C.c_uint32],'credit':[C.c_uint,C.c_uint32],'poll':[C.c_uint32],'sample':[C.c_uint8,C.c_uint,C.c_uint32],'done':[C.c_uint8,C.c_uint8,C.c_uint32],'cancel':[C.c_uint8]}.items():
            f=getattr(cls.lib,'wifi_tx_timing_'+name);f.argtypes=[C.POINTER(State)]+args;f.restype=None
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):self.s=State();self.call('reset')
    def call(self,name,*args):getattr(self.lib,'wifi_tx_timing_'+name)(C.byref(self.s),*args)
    def test_credit_isolated_full_return_and_size_bins(self):
        for size,base,delay in ((7,100,12),(1,200,8),(7,300,16)):
            self.call('begin',size,base);self.call('written',base+2)
            for free in (0,12,13,15):self.call('credit',free,base+3)
            self.assertEqual(self.s.active,1)
            self.call('credit',14,base+delay);self.call('credit',14,base+99)
        b=self.s.bin[6]
        self.assertEqual((b.credits,b.credit_sum,b.credit_min,b.credit_max,b.writes,b.write_sum),(2,28,12,16,2,4))
        self.assertEqual(self.s.bin[0].credit_sum,8)
        self.assertEqual(self.s.active,0)
    def test_unicast_or_overlapping_sample_excludes_credit(self):
        self.call('begin',3,10);self.call('other');self.call('credit',14,20)
        self.assertEqual(self.s.bin[2].credits,0)
        self.call('begin',1,30);self.call('begin',7,40);self.call('credit',14,50)
        self.assertEqual(self.s.excluded,2);self.assertEqual(self.s.bin[0].credits,0)
        self.assertEqual(self.s.bin[6].credits,1)
    def test_callback_identity_status_duplicate_and_cancellation(self):
        self.call('sample',128,7,10);self.call('sample',129,1,20)
        self.call('done',0,0,30);self.call('done',130,0,30)
        self.call('done',128,2,40);self.call('done',128,0,50)
        b=self.s.bin[6];self.assertEqual((b.done,b.done_sum,b.done_failed),(1,30,1))
        self.call('cancel',129);self.call('done',129,0,60)
        self.assertEqual(self.s.bin[0].done,0)
    def test_wrap_and_invalid_sizes_and_reset(self):
        self.call('begin',0,1);self.call('begin',8,2);self.assertEqual(self.s.active,0)
        self.call('begin',3,0xfffffffc);self.call('written',0xffffffff);self.call('credit',14,4)
        self.call('sample',255,3,0xfffffffe);self.call('done',255,0,3)
        b=self.s.bin[2];self.assertEqual((b.credit_sum,b.write_sum,b.done_sum),(8,3,5))
        self.call('reset');self.assertEqual(bytes(self.s),bytes(C.sizeof(State)))
    def test_poll_density_gaps_tail_and_wrap(self):
        self.call('poll',99);self.call('begin',7,0xfffffffc)
        for now in (0xfffffffd,0xfffffffd,0):self.call('poll',now)
        self.call('credit',13,1);self.assertEqual(self.s.bin[6].credits,0)
        self.call('credit',14,2)
        b=self.s.bin[6]
        self.assertEqual((b.poll_sum,b.poll_min,b.poll_max,b.poll_gap_max),(3,3,3,3))
        self.call('begin',7,100);self.call('poll',104);self.call('credit',14,110)
        self.assertEqual((b.poll_sum,b.poll_min,b.poll_max,b.poll_gap_max),(4,1,3,6))
        self.call('begin',7,200);self.call('poll',250);self.call('other');self.call('credit',14,260)
        self.assertEqual((b.poll_sum,b.poll_gap_max),(4,6))
if __name__=='__main__':unittest.main()
