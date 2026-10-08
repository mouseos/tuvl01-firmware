import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AP = bytes.fromhex('020000000002')
RSN = bytes.fromhex('30140100000fac040100000fac040100000fac020000')
RATES = bytes.fromhex('010882848b968c1298243204b048606c')
SSID = b'\0\4test'
DS = b'\3\1\6'
TIM = b'\5\4\1\3\0\0'
ERP = b'\x2a\1\6'
HEADER = b'\x80\0\0\0'+bytes([255])*6+AP+AP+bytes(2)+bytes(8)+b'\x64\0\x31\x04'


class Beacon(C.Structure):
    _fields_ = [('ap', C.c_uint8*6), ('ssid', C.c_uint8*32), ('rsn', C.c_uint8*257),
                ('interval', C.c_uint16), ('capability', C.c_uint16),
                ('operational', C.c_uint16), ('basic', C.c_uint16), ('rsn_length', C.c_uint16),
                ('ssid_length', C.c_uint8), ('channel', C.c_uint8), ('rx_channel', C.c_uint8),
                ('tim_present', C.c_uint8), ('dtim_count', C.c_uint8), ('dtim_period', C.c_uint8),
                ('short_preamble', C.c_uint8), ('short_slot', C.c_uint8), ('erp_protection', C.c_uint8)]


class Discovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); lib = pathlib.Path(cls.tmp.name)/'beacon.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT/'include'), str(ROOT/'src/wifi_ais_beacon.c'),
                        str(ROOT/'src/wifi_rates.c'), str(ROOT/'src/wifi_channel.c'),
                        '-o', str(lib)], check=True)
        cls.c = C.CDLL(str(lib))
        cls.c.wifi_ais_beacon_parse.argtypes = [C.c_void_p, C.c_uint, C.c_uint,
                                              C.c_void_p, C.c_uint, C.POINTER(Beacon)]
        cls.c.wifi_channel_request_ais.argtypes = [C.c_void_p, C.c_uint, C.c_uint,
                                                C.c_uint, C.c_uint32, C.c_void_p]
        cls.c.wifi_channel_grant_ais.argtypes = [C.c_void_p, C.c_uint, C.c_uint,
                                              C.c_uint, C.POINTER(C.c_uint32)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def parse(self, p, channel=6, expected=AP, profile=0):
        r = Beacon(); C.memset(C.byref(r), 165, C.sizeof(r))
        ok = self.c.wifi_ais_beacon_parse(p, len(p), channel, expected, profile, C.byref(r))
        return ok, r

    def test_copies_beacon_parameters_and_rsn_before_fifo_reuse(self):
        p = C.create_string_buffer(HEADER+SSID+RATES+DS+TIM+ERP+RSN)
        r = Beacon()
        self.assertEqual(self.c.wifi_ais_beacon_parse(p, len(p)-1, 6, AP, 0, C.byref(r)), 1)
        C.memset(p, 0, len(p))
        self.assertEqual(bytes(r.ap), AP)
        self.assertEqual(bytes(r.ssid[:r.ssid_length]), b'test')
        self.assertEqual(bytes(r.rsn[:r.rsn_length]), RSN)
        self.assertEqual((r.interval, r.capability, r.operational, r.basic), (100, 0x431, 0x3fcf, 0x054f))
        self.assertEqual((r.channel, r.rx_channel, r.tim_present, r.dtim_count, r.dtim_period), (6, 6, 1, 1, 3))
        self.assertEqual((r.short_preamble, r.short_slot, r.erp_protection), (0, 1, 1))

    def test_missing_tim_and_rsn_explicit_hidden_ssid_supported(self):
        ok, r = self.parse(HEADER+b'\0\0'+RATES)
        self.assertEqual(ok, 1)
        self.assertEqual((r.ssid_length, r.tim_present, r.dtim_period, r.rsn_length), (0, 0, 0, 0))
        self.assertEqual((r.short_preamble, r.short_slot, r.channel), (1, 1, 6))

    def test_radio_and_advertised_channel_are_kept_separate(self):
        ok, r = self.parse(HEADER+SSID+RATES+DS, channel=5, expected=None)
        self.assertEqual(ok, 1)
        self.assertEqual((r.channel, r.rx_channel), (6, 5))
        self.assertEqual(self.parse(HEADER+SSID+RATES+DS, expected=b'\x02'+bytes(5))[0], 0)

    def test_wrong_headers_and_unsupported_basic_rates_rejected(self):
        good = HEADER+SSID+RATES+DS
        for pos, value in [(0, 0x50), (1, 1), (1, 4), (1, 64), (1, 128),
                           (4, 2), (10, 3), (16, 3), (22, 1), (32, 0), (34, 2)]:
            bad = bytearray(good); bad[pos] = value
            ok, r = self.parse(bytes(bad))
            self.assertEqual(ok, 0, (pos, value))
            self.assertEqual((r.interval, r.rsn_length, r.tim_present), (0, 0, 0))
        self.assertEqual(self.parse(good, profile=1)[0], 0)
        self.assertEqual(self.parse(HEADER+SSID+b'\1\1\xff')[0], 0)
        self.assertEqual(self.parse(HEADER+SSID+b'\1\1\x0c')[0], 0)  # no basic rates

    def test_duplicate_known_ies_and_truncated_lists_rejected(self):
        base = HEADER+SSID+RATES+DS+TIM+ERP+RSN
        for ie in (SSID, RATES[:10], RATES[10:], DS, TIM, ERP, RSN):
            self.assertEqual(self.parse(base+ie)[0], 0)
        for n in range(36):
            self.assertEqual(self.parse(base[:n])[0], 0)
        self.assertEqual(self.parse(base[:-1])[0], 0)
        self.assertEqual(self.parse(base+b'\xdd')[0], 0)

    def test_invalid_dtim_channel_and_rsn_version_rejected(self):
        for ie in (b'\3\1\0', b'\3\1\x0e', b'\5\4\0\0\0\0',
                   b'\5\4\3\3\0\0', b'\5\3\0\1\0', b'\x2a\0',
                   b'\x30\2\2\0'):
            self.assertEqual(self.parse(HEADER+SSID+RATES+ie)[0], 0)
        for channel in (0, 14, 255):
            self.assertEqual(self.parse(HEADER+SSID+RATES, channel=channel)[0], 0)

    def test_ais_join_channel_request_full_wire_and_alias(self):
        out = C.create_string_buffer(28)
        for channel in range(1, 14):
            self.assertEqual(self.c.wifi_channel_request_ais(out, 28, channel, 7, 4000, AP), 1)
            expected = bytes(8)+bytes([0, 7, 0, channel, 0, 1, 0, 0])+b'\xa0\x0f\0\0'+AP+bytes(2)
            self.assertEqual(out.raw, expected)
        out[0:6] = AP
        self.assertEqual(self.c.wifi_channel_request_ais(out, 28, 6, 7, 4000, out), 1)
        self.assertEqual(out.raw[20:26], AP)
        for channel, token, interval, ap in [(0, 7, 4000, AP), (14, 7, 4000, AP),
                    (6, 0, 4000, AP), (6, 256, 4000, AP), (6, 7, 0, AP),
                    (6, 7, 60001, AP), (6, 7, 4000, bytes(6))]:
            old = out.raw
            self.assertEqual(self.c.wifi_channel_request_ais(out, 28, channel, token, interval, ap), 0)
            self.assertEqual(out.raw, old)

    def test_ais_channel_grant_correlation_and_actual_lease(self):
        p = bytes([20, 0, 1, 0, 0x18, 0, 0, 0, 0, 7, 0, 6, 0, 1, 0, 0])+b'\xdc\x05\0\0'
        interval = C.c_uint32(99)
        self.assertEqual(self.c.wifi_channel_grant_ais(p, 20, 6, 7, C.byref(interval)), 1)
        self.assertEqual(interval.value, 1500)
        for pos, value in [(0, 19), (2, 0), (4, 1), (8, 1), (9, 8), (10, 1),
                           (11, 5), (12, 1), (13, 2), (14, 1), (18, 1)]:
            bad = bytearray(p); bad[pos] = value
            self.assertEqual(self.c.wifi_channel_grant_ais(bytes(bad), 20, 6, 7, C.byref(interval)), 0)
            self.assertEqual(interval.value, 0)
        self.assertEqual(self.c.wifi_channel_grant_ais(p[:-1], 19, 6, 7, C.byref(interval)), 0)
        self.assertEqual(self.c.wifi_channel_grant_ais(p, 20, 6, 7, None), 0)


if __name__ == '__main__':
    unittest.main()
