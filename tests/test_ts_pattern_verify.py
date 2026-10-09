import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from ts_pattern_verify import expected_byte,verify
class Verify(unittest.TestCase):
    def test_multiple_batches_and_partial_final_batch(self):
        data=bytes(expected_byte(n) for n in range(6016*3+188*7))
        self.assertEqual(verify(data)['errors'],0)
    def test_corruption_and_dropped_packet_are_detected(self):
        data=bytearray(expected_byte(n) for n in range(6016*2));data[193]^=1
        self.assertEqual(verify(data)['errors'],1);self.assertEqual(verify(data)['first_offset'],193)
        self.assertGreater(verify(data[188:])['errors'],0)
    def test_empty_and_partial_packet_rejected(self):
        for data in [b'',b'x'*189]:
            with self.assertRaises(ValueError):verify(data)
if __name__=='__main__':unittest.main()
