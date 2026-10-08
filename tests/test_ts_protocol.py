import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class Status(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        library=pathlib.Path(cls.tmp.name)/'ts_protocol.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/ts_protocol.c'),'-o',str(library)],check=True)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.tuner_ts_classify.argtypes=[ctypes.c_uint8]
        cls.lib.tuner_ts_classify.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_empty_ready_and_documented_errors(self):
        for byte,expected in ((0,0),(1,1),(2,-2),(3,-2),(4,-3),(5,-3),(6,-2),(7,-2)):
            self.assertEqual(self.lib.tuner_ts_classify(byte),expected)
    def test_disconnected_or_reserved_status_cannot_be_ready(self):
        for byte in range(8,256):
            self.assertEqual(self.lib.tuner_ts_classify(byte),-4)

if __name__=='__main__':unittest.main()
