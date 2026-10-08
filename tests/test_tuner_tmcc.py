import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Layer(ctypes.Structure):_fields_=[(n,ctypes.c_uint8) for n in ('modulation','code_rate','interleave','segments')]
class Info(ctypes.Structure):_fields_=[(n,ctypes.c_uint8) for n in ('system','countdown','emergency','partial','phase')]+[('layer',Layer*3)]
class TMCC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();library=pathlib.Path(cls.tmp.name)/'tmcc.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/tuner_tmcc_protocol.c'),'-o',str(library)],check=True)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.tuner_tmcc_decode.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.POINTER(Info)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_reference_register_field_layout(self):
        raw=(ctypes.c_uint8*8)(0x1e,0x49,0x31,0x1a,0x2c,0x3f,0x7f,5);i=Info()
        self.lib.tuner_tmcc_decode(raw,ctypes.byref(i))
        self.assertEqual((i.system,i.countdown,i.emergency,i.partial,i.phase),(0,15,0,1,5))
        self.assertEqual([(l.modulation,l.code_rate,l.interleave,l.segments) for l in i.layer],[(1,1,3,1),(3,2,2,12),(7,7,7,15)])
