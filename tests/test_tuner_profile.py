import ctypes,pathlib,subprocess,tempfile,unittest,zlib,struct
ROOT=pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'tools'))
from tune import encode

class Profile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        library=pathlib.Path(cls.tmp.name)/'profile.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/tuner_profile_protocol.c'),'-o',str(library)],check=True)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.tuner_profile_valid.argtypes=[ctypes.POINTER(ctypes.c_uint8)]
        cls.lib.tuner_profile_valid.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def valid(self,data):return self.lib.tuner_profile_valid((ctypes.c_uint8*32).from_buffer_copy(data))
    def profile(self):
        # Synthetic protocol test values: not a hardware profile.
        return dict(mode='uhf-partial-experimental',rf_khz=600000,fad=1,nco=0,sysset=16,p_m=32,p_k=0x12345,tncop1=1,tncop2=2,tncop3=3,tncop4=4,tncop6=8,tncop7=64,adclksel=113,dtvset=64)
    def test_host_and_target_agree(self):
        p=encode(self.profile());self.assertEqual(len(p),32);self.assertEqual(self.valid(p),1)
    def test_native_uf_mode_requires_explicit_pscop(self):
        profile=self.profile();profile.update(mode='uhf-native-candidate',dtvset=0x16)
        p=encode(profile);self.assertEqual(p[27],2);self.assertEqual(self.valid(p),1)
        profile['dtvset']=0x40
        with self.assertRaises(ValueError):encode(profile)
        q=bytearray(p);q[26]=0x40;q[28:]=struct.pack('>I',zlib.crc32(q[:28]))
        self.assertEqual(self.valid(q),0)
    def test_all_single_bit_corruptions_rejected(self):
        p=encode(self.profile())
        for bit in range(256):
            changed=bytearray(p);changed[bit//8]^=1<<(bit%8)
            self.assertEqual(self.valid(changed),0)
    def test_recomputed_crc_does_not_bypass_target_bounds(self):
        p=bytearray(encode(self.profile()))
        for offset,values in ((27,(2,255)),(16,(16,255)),(15,(0,)),(26,(0,192))):
            for value in values:
                q=bytearray(p);q[offset]=value;q[28:]=struct.pack('>I',zlib.crc32(q[:28]))
                self.assertEqual(self.valid(q),0)
        for freq in (0,469999,770001,0xffffffff):
            q=bytearray(p);q[4:8]=struct.pack('>I',freq);q[28:]=struct.pack('>I',zlib.crc32(q[:28]))
            self.assertEqual(self.valid(q),0)
    def test_host_rejects_invalid_frequency_before_transport(self):
        p=self.profile();p['rf_khz']=0
        with self.assertRaises(ValueError):encode(p)
