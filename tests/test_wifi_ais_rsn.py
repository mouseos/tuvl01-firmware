import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RSN = bytes.fromhex('30140100000fac040100000fac040100000fac020000')

class RsnSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = pathlib.Path(cls.tmp.name) / 'rsn.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT/'include'), str(ROOT/'src/wifi_ais_rsn.c'),
                        '-o', str(lib)], check=True)
        cls.lib = C.CDLL(str(lib))
        cls.lib.wifi_ais_rsn_select.argtypes = [C.c_void_p, C.c_uint, C.c_void_p, C.c_uint]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def select(self, data, capacity=22):
        out = C.create_string_buffer(b'X'*22, 22)
        n = self.lib.wifi_ais_rsn_select(data, len(data), out, capacity)
        return n, out.raw

    def refused(self, data):
        self.assertEqual(self.select(data), (0, b'X'*22))

    def test_explicit_ccmp_psk_and_optional_fields(self):
        for suffix in (b'', b'\0\0', b'\x80\0', b'\x80\0\0\0',
                       b'\x80\0\0\0\0\x0f\xac\6'):
            data = bytearray(RSN[:20]+suffix); data[1] = len(data)-2
            self.assertEqual(self.select(bytes(data)), (22, RSN))

    def test_mixed_lists_select_only_supported_suite(self):
        data = bytes.fromhex('301c0100000fac040200000fac02000fac040200000fac01000fac020000')
        self.assertEqual(self.select(data), (22, RSN))

    def test_refuses_other_group_pairwise_akm_and_required_mfp(self):
        for pos, value in ((7, 2), (13, 2), (19, 1), (20, 64), (2, 2), (0, 221)):
            data = bytearray(RSN); data[pos] = value
            self.refused(bytes(data))
        data = bytearray(RSN); data[20] = 0xc0
        self.refused(bytes(data))

    def test_counts_lengths_and_all_truncations(self):
        for n in range(len(RSN)):
            self.refused(RSN[:n])
        for pos in (8, 14):
            for count in (0, 2, 255):
                data = bytearray(RSN); data[pos] = count
                self.refused(bytes(data))
        for suffix in (b'\0', b'\0\0\0', b'\0\0\1\0',
                       b'\0\0\1\0'+b'A'*16, b'\0\0\0\0\0\x0f\xac\7',
                       b'\0\0\0\0\0\x0f\xac\6\0'):
            data = bytearray(RSN[:20]+suffix); data[1] = len(data)-2
            self.refused(bytes(data))

    def test_output_capacity_null_and_aliasing(self):
        self.assertEqual(self.select(RSN, 21), (0, b'X'*22))
        out = C.create_string_buffer(RSN, 22)
        self.assertEqual(self.lib.wifi_ais_rsn_select(out, 22, out, 22), 22)
        self.assertEqual(out.raw, RSN)
        self.assertEqual(self.lib.wifi_ais_rsn_select(None, 22, out, 22), 0)
        self.assertEqual(self.lib.wifi_ais_rsn_select(RSN, 22, None, 22), 0)

if __name__ == '__main__':
    unittest.main()
