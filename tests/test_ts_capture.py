import pathlib,sys,unittest,zlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from ts_capture import inspect,validate_capture
def packet(pid=0x100,cc=0):return bytes([0x47,pid>>8,pid&255,0x10|cc])+bytes(184)
class Capture(unittest.TestCase):
    def test_valid_headers_and_wraparound(self):
        data=packet(cc=15)+packet(cc=0)+packet(pid=0x1fff,cc=9)+packet(pid=0x1fff,cc=3)
        report=inspect(data)
        self.assertEqual(report['continuity_errors'],0);self.assertEqual(report['sync_errors'],0)
        validate_capture(data,4,zlib.crc32(data))
    def test_corruption_and_length_mismatch(self):
        data=packet()
        for count,crc in ((2,zlib.crc32(data)),(1,zlib.crc32(data)^1),(129,zlib.crc32(data))):
            with self.assertRaises(ValueError):validate_capture(data,count,crc)
    def test_bad_sync_tei_and_adaptation(self):
        bad=bytearray(packet());bad[0]=0
        tei=bytearray(packet());tei[1]|=128
        af=bytearray(packet());af[3]=0x30;af[4]=183
        r=inspect(bad+tei+af)
        self.assertEqual((r['sync_errors'],r['tei_errors'],r['adaptation_errors']),(1,1,1))
    def test_continuity_gap_and_explicit_discontinuity(self):
        self.assertEqual(inspect(packet(cc=1)+packet(cc=4))['continuity_errors'],1)
        reset=bytearray(packet(cc=4));reset[3]=0x34;reset[4]=1;reset[5]=128
        self.assertEqual(inspect(packet(cc=1)+reset)['continuity_errors'],0)
    def test_same_counter_requires_identical_duplicate(self):
        p=packet(cc=1);changed=bytearray(p);changed[100]=1
        self.assertEqual(inspect(p+p)['continuity_errors'],0)
        self.assertEqual(inspect(p+changed)['continuity_errors'],1)
