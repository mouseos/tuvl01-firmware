import ctypes
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OWN = bytes.fromhex('020000000001')
AP = bytes.fromhex('020000000002')
RSN = bytes.fromhex('30140100000fac040100000fac040100000fac020000')
RATES = bytes.fromhex('010882848b968c1298243204b048606c')


class Assoc(ctypes.Structure):
    _fields_ = [('status', ctypes.c_uint16), ('capability', ctypes.c_uint16),
                ('aid', ctypes.c_uint16), ('operational', ctypes.c_uint16),
                ('basic', ctypes.c_uint16), ('ies', ctypes.c_void_p),
                ('ie_length', ctypes.c_uint)]


class AIS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = pathlib.Path(cls.tmp.name) / 'ais.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT/'include'), str(ROOT/'src/wifi_ais_mgmt.c'),
                        str(ROOT/'src/wifi_rates.c'), '-o', str(lib)], check=True)
        cls.c = ctypes.CDLL(str(lib))
        ptr, u = ctypes.c_void_p, ctypes.c_uint
        cls.c.wifi_ais_auth_request.argtypes = [ptr, ptr, u, ptr, u]
        cls.c.wifi_ais_auth_response.argtypes = [ptr, u, ptr, ptr, ctypes.POINTER(ctypes.c_uint16)]
        cls.c.wifi_ais_assoc_request.argtypes = [ptr, ptr, u, ctypes.c_uint16,
                ctypes.c_uint16, ptr, u, ptr, u, u, ptr, u]
        cls.c.wifi_ais_assoc_response.argtypes = [ptr, u, ptr, ptr, u, ctypes.POINTER(Assoc)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def header(self, subtype):
        return bytes([subtype, 0, 0, 0])+OWN+AP+AP+b'\x20\0'

    def assoc(self, p, profile=0):
        result = Assoc(1, 2, 3, 4, 5, 123, 7)
        ok = self.c.wifi_ais_assoc_response(p, len(p), OWN, AP, profile, ctypes.byref(result))
        return ok, result

    def test_auth_is_open_system_even_with_wpa2(self):
        out = ctypes.create_string_buffer(30)
        self.assertEqual(self.c.wifi_ais_auth_request(OWN, AP, 0xabc, out, 30), 30)
        self.assertEqual(out.raw, b'\xb0\0\0\0'+AP+OWN+AP+b'\xc0\xab'+b'\0\0\1\0\0\0')
        status = ctypes.c_uint16()
        for value in (0, 13):
            p = self.header(0xb0)+b'\0\0\2\0'+value.to_bytes(2, 'little')
            self.assertEqual(self.c.wifi_ais_auth_response(p, len(p), OWN, AP, ctypes.byref(status)), 1)
            self.assertEqual(status.value, value)
        p = self.header(0xb0)+b'\0\0\1\0\0\0'
        self.assertEqual(self.c.wifi_ais_auth_response(p, 30, OWN, AP, ctypes.byref(status)), 0)
        self.assertEqual(status.value, 0xffff)

    def test_assoc_request_contains_supplicant_ie_and_actual_parameters(self):
        out = ctypes.create_string_buffer(512)
        n = self.c.wifi_ais_assoc_request(OWN, AP, 4095, 0x431, 3,
                b'test', 4, RSN, len(RSN), 0, out, 512)
        expected = b'\0\0\0\0'+AP+OWN+AP+b'\xf0\xff'+b'\x31\x04\3\0\0\4test'+RATES+RSN
        self.assertEqual(n, len(expected))
        self.assertEqual(out.raw[:n], expected)

    def test_success_uses_ap_aid_capability_and_rate_sets(self):
        p = self.header(0x10)+bytes.fromhex('3104000023c1')+RATES
        ok, r = self.assoc(p)
        self.assertEqual(ok, 1)
        self.assertEqual((r.status, r.capability, r.aid, r.operational, r.basic),
                         (0, 0x431, 0x123, 0x3fcf, 0x054f))
        self.assertEqual(ctypes.string_at(r.ies, r.ie_length), RATES)

    def test_rejection_is_not_association(self):
        ok, r = self.assoc(self.header(0x10)+bytes.fromhex('310411000000'))
        self.assertEqual(ok, 1)
        self.assertEqual((r.status, r.aid, r.operational, r.basic), (17, 0, 0, 0))

    def test_wrong_peer_flags_fragments_aid_and_capabilities_rejected(self):
        good = self.header(0x10)+bytes.fromhex('3104000001c0')+RATES
        for pos, value in [(0, 0x30), (1, 1), (1, 4), (1, 64), (1, 128),
                           (4, 3), (10, 3), (16, 3), (22, 1), (24, 2),
                           (28, 0), (29, 0), (28, 0xff)]:
            bad = bytearray(good); bad[pos] = value
            # 0xc0ff is a valid AID; test >2007 with high byte 0xc8 instead.
            if pos == 28 and value == 0xff: bad[29] = 0xc8
            ok, r = self.assoc(bytes(bad))
            self.assertEqual(ok, 0, (pos, value))
            self.assertEqual((r.aid, r.ies, r.ie_length), (0, None, 0))
        bad = bytearray(good); bad[1] = 8  # retry is legal
        self.assertEqual(self.assoc(bytes(bad))[0], 1)

    def test_malformed_duplicate_and_unsupported_basic_rates_rejected(self):
        fixed = self.header(0x10)+bytes.fromhex('3104000001c0')
        for ies in (b'', b'\x01', b'\x01\0', b'\x01\x09'+bytes(9),
                    RATES+RATES, b'\x01\x01\xff', RATES+b'\xdd\x02\0'):
            self.assertEqual(self.assoc(fixed+ies)[0], 0)
        self.assertEqual(self.assoc(fixed+RATES, profile=1)[0], 0)  # CCK basic not supported by ERP-only
        self.assertEqual(self.assoc(fixed+bytes.fromhex('01018c'))[0], 1)
        for n in range(30):
            self.assertEqual(self.assoc((fixed+RATES)[:n])[0], 0)

    def test_invalid_requests_leave_output_untouched(self):
        out = ctypes.create_string_buffer(b'X'*512, 512)
        cases = [(OWN, AP, 4096, 0x431, 1, b'test', 4, RSN, len(RSN), 0, 512),
                 (OWN, OWN, 0, 0x431, 1, b'test', 4, RSN, len(RSN), 0, 512),
                 (OWN, AP, 0, 0x401, 1, b'test', 4, RSN, len(RSN), 0, 512),
                 (OWN, AP, 0, 0x431, 0, b'test', 4, RSN, len(RSN), 0, 512),
                 (OWN, AP, 0, 0x431, 1, None, 0, RSN, len(RSN), 0, 512),
                 (OWN, AP, 0, 0x431, 1, b'test', 4, RSN, len(RSN)-1, 0, 512),
                 (OWN, AP, 0, 0x431, 1, b'test', 4, RSN, len(RSN), 0, 30)]
        for args in cases:
            self.assertEqual(self.c.wifi_ais_assoc_request(*args[:-1], out, args[-1]), 0)
            self.assertEqual(out.raw, b'X'*512)
        self.assertEqual(self.c.wifi_ais_auth_request(OWN, AP, 0, out, 29), 0)
        self.assertEqual(out.raw, b'X'*512)

    def test_input_output_overlap_rejected_before_writing(self):
        out = ctypes.create_string_buffer(512)
        out[0:6] = OWN
        before = out.raw
        self.assertEqual(self.c.wifi_ais_auth_request(out, AP, 0, out, 512), 0)
        self.assertEqual(out.raw, before)
        self.assertEqual(self.c.wifi_ais_assoc_request(OWN, AP, 0, 0x431, 1,
                        out, 4, RSN, len(RSN), 0, out, 512), 0)
        self.assertEqual(out.raw, before)


if __name__ == '__main__':
    unittest.main()
