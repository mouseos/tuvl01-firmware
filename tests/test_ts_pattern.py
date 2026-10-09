import ctypes,pathlib,subprocess,tempfile,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from ts_capture import inspect

class Pattern(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();path=pathlib.Path(cls.tmp.name)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
                        '-I'+str(ROOT/'include'),str(ROOT/'src/ts_pattern.c'),
                        '-o',str(path/'pattern.so')],check=True)
        cls.lib=ctypes.CDLL(str(path/'pattern.so'))
        cls.lib.ts_pattern_fill.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        cls.lib.ts_pattern_fill.restype=ctypes.c_uint
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_repeated_batches_have_continuity_and_no_scrambling(self):
        output=(ctypes.c_uint8*(32*188+8))(*([0xa5]*(32*188+8)))
        self.assertEqual(self.lib.ts_pattern_fill(output,len(output)),32)
        self.assertEqual(bytes(output[-8:]),b'\xa5'*8)
        batch=bytes(output[:-8]);result=inspect(batch*3)
        self.assertEqual(result['packets'],96)
        self.assertEqual(result['pids'],{'0x1ffe':96})
        self.assertEqual(result['continuity_comparisons'],95)
        for key in ('sync_errors','tei_errors','adaptation_errors','continuity_errors'):
            self.assertEqual(result[key],0)
        for i in range(32):
            self.assertEqual(batch[i*188:(i+1)*188],bytes((0x47,0x1f,0xfe,0x10|(i&15)))+b'\xff'*184)
    def test_short_and_null_rejected_without_write(self):
        output=(ctypes.c_uint8*(32*188))(*([0xa5]*(32*188)))
        for capacity in (0,32*188-1):
            self.assertEqual(self.lib.ts_pattern_fill(output,capacity),0)
            self.assertEqual(bytes(output),b'\xa5'*(32*188))
        self.assertEqual(self.lib.ts_pattern_fill(None,32*188),0)

    def test_dma_pattern_matches_pc_verifier_and_bounds(self):
        from ts_pattern_verify import verify
        self.lib.ts_pattern_dma_fill.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        out=(ctypes.c_uint8*(6016+8))(*([0xa5]*(6016+8)))
        self.assertEqual(self.lib.ts_pattern_dma_fill(out,6015),0)
        self.assertEqual(bytes(out),b'\xa5'*len(out))
        self.assertEqual(self.lib.ts_pattern_dma_fill(None,6016),0)
        self.assertEqual(self.lib.ts_pattern_dma_fill(out,len(out)),32)
        self.assertEqual(bytes(out[-8:]),b'\xa5'*8)
        self.assertEqual(verify(bytes(out[:6016])*3)['errors'],0)
if __name__=='__main__':unittest.main()
