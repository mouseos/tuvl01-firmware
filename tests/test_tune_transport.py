import pathlib,sys,unittest
from unittest.mock import Mock,patch,call
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from tune import send_profile

class ProfileTransport(unittest.TestCase):
    def test_pacing_preserves_all_bytes_including_zero(self):
        t=Mock();data=bytes(range(32))
        with patch('tune.time.sleep') as sleep:
            send_profile(t,data)
        self.assertEqual(t.write.call_args_list,[call(bytes([x])) for x in data])
        self.assertEqual(sleep.call_args_list,[call(.01)]*32)
    def test_bad_length_sends_nothing(self):
        t=Mock()
        with self.assertRaises(ValueError):send_profile(t,b'bad')
        t.write.assert_not_called()
