"""Check IEEE rate advertisements, protocol masks and bounded serialization."""
import ctypes as C,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Rates(C.Structure):
    _fields_=[('operational',C.c_uint16),('basic',C.c_uint16),('phy',C.c_uint8),('ies',C.c_void_p),('length',C.c_uint)]
class Profiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)/'rates.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/wifi_rates.c'),'-o',str(p)],check=True)
        cls.c=C.CDLL(str(p));cls.c.wifi_rates_get.argtypes=[C.c_uint];cls.c.wifi_rates_get.restype=C.POINTER(Rates)
        cls.c.wifi_rates_ies.argtypes=[C.c_uint,C.c_uint,C.c_void_p,C.c_uint];cls.c.wifi_rates_ies.restype=C.c_uint
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_masks_match_advertised_rates_and_basic_flags(self):
        code_bits={2:0,4:1,11:2,22:3,12:6,18:7,24:8,36:9,48:10,72:11,96:12,108:13}
        for profile in (0,1):
            r=self.c.wifi_rates_get(profile).contents;ies=C.string_at(r.ies,r.length);op=basic=0;pos=0
            while pos<len(ies):
                self.assertIn(ies[pos],(1,50));n=ies[pos+1]
                for rate in ies[pos+2:pos+2+n]:
                    op|=1<<code_bits[rate&127]
                    if rate&128:basic|=1<<code_bits[rate&127]
                    if profile:self.assertGreaterEqual(rate&127,12);self.assertNotIn(rate&127,(22,))
                pos+=2+n
            self.assertEqual((r.operational,r.basic),(op,basic))
            self.assertEqual(r.phy,2 if profile else 3)
    def test_beacon_default_bytes_and_erp_no_legacy_rates(self):
        expected=(bytes.fromhex('00065455564c3031010882848b968c1298243204b048606c0301010504000100002a0100'),bytes.fromhex('00065455564c303101088c129824b048606c0301010504000100002a0100'))
        for profile in (0,1):
            out=(C.c_uint8*48)(*([165]*48));n=self.c.wifi_rates_ies(profile,1,out,48)
            self.assertEqual(bytes(out[:n]),expected[profile]);self.assertEqual(bytes(out[n:]),bytes([165])*(48-n))
    def test_capacity_kind_and_profile_rejection_leave_sentinel(self):
        for profile,kind,capacity in ((0,1,35),(1,1,29),(0,3,48),(2,0,48)):
            out=(C.c_uint8*48)(*([165]*48));self.assertEqual(self.c.wifi_rates_ies(profile,kind,out,capacity),0)
            self.assertEqual(bytes(out),bytes([165])*48)
        self.assertEqual(self.c.wifi_rates_ies(0,1,None,48),0);self.assertFalse(self.c.wifi_rates_get(2))
if __name__=='__main__':unittest.main()
