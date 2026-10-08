import ctypes,pathlib,struct,subprocess,tempfile,unittest,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]

def packet(seconds,magic=b'TSB1'):
    data=magic+struct.pack('>I',seconds)
    return data+struct.pack('>I',zlib.crc32(data))

class Duration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        path=pathlib.Path(cls.tmp.name)/'duration.so'
        subprocess.run(['cc','-shared','-fPIC','-Wl,-Bsymbolic','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(ROOT/'src/ts_benchmark_protocol.c'),
            str(ROOT/'src/image.c'),'-o',str(path)],check=True)
        cls.lib=ctypes.CDLL(str(path))
        cls.lib.ts_benchmark_seconds.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        cls.lib.ts_benchmark_seconds.restype=ctypes.c_uint
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def duration(self,data):return self.lib.ts_benchmark_seconds(data,len(data))
    def test_seconds_boundaries_and_long_window(self):
        for seconds in (1,10,60,120,300):
            self.assertEqual(self.duration(packet(seconds)),seconds)
    def test_recomputed_crc_does_not_allow_unbounded_duration_or_version(self):
        for seconds in (0,301,0xffffffff):
            self.assertEqual(self.duration(packet(seconds)),0)
        self.assertEqual(self.duration(packet(60,b'TSB2')),0)
    def test_all_single_bit_corruptions_rejected(self):
        good=packet(60)
        for bit in range(96):
            data=bytearray(good);data[bit//8]^=1<<(bit%8)
            self.assertEqual(self.duration(bytes(data)),0)
    def test_null_truncation_and_trailing_bytes_rejected(self):
        good=packet(60)
        self.assertEqual(self.lib.ts_benchmark_seconds(None,12),0)
        for length in range(12):self.assertEqual(self.duration(good[:length]),0)
        self.assertEqual(self.duration(good+b'\0'),0)

if __name__=='__main__':unittest.main()
