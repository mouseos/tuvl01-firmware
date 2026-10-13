"""In-firmware UHF channel profiles must equal what tools/tune.py sends over UART."""
import ctypes,json,os,pathlib,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from tune import encode
EXTERNAL=os.environ.get('TUVL01_PROFILE_DIR')  # optional: all 40 generated channels
def load(path):return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))
class Uhf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
            str(ROOT/'src/tuner_uhf.c'),str(ROOT/'src/tuner_uhf_table.c'),str(ROOT/'src/tuner_profile_protocol.c'),
            '-o',str(p/'uhf.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'uhf.so'))
        cls.c.tuner_uhf_profile.argtypes=[ctypes.c_uint,ctypes.c_uint,ctypes.c_char_p]
        cls.c.tuner_profile_valid.argtypes=[ctypes.c_char_p]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def build(self,ch,partial):
        out=ctypes.create_string_buffer(32);rc=self.c.tuner_uhf_profile(ch,partial,out);return rc,out.raw
    def test_matches_stored_profiles(self):
        for name,ch,partial in (('uhf-ch14-full',14,0),('uhf-ch14-partial',14,1),('uhf-ch19-full',19,0)):
            rc,raw=self.build(ch,partial);self.assertEqual(rc,0)
            self.assertEqual(raw,encode(load(ROOT/'profiles'/(name+'.json'))),name)
    def test_every_channel_is_a_valid_profile_in_both_modes(self):
        for ch in range(13,53):
            for partial in (0,1):
                rc,raw=self.build(ch,partial);self.assertEqual(rc,0)
                self.assertTrue(self.c.tuner_profile_valid(raw),(ch,partial))
                freq=int.from_bytes(raw[4:8],'big');self.assertEqual(freq,473143+6000*(ch-13))
    def test_outside_range_is_refused(self):
        for ch in (0,12,53,255):self.assertEqual(self.build(ch,0)[0],-1)
    @unittest.skipUnless(EXTERNAL,'set TUVL01_PROFILE_DIR to compare all generated channels')
    def test_all_generated_channels_match(self):
        for ch in range(13,53):
            for partial,suffix in ((0,'full'),(1,'partial')):
                self.assertEqual(self.build(ch,partial)[1],encode(load(pathlib.Path(EXTERNAL)/f'uhf-ch{ch}-{suffix}.json')),(ch,suffix))
if __name__=='__main__':unittest.main()
