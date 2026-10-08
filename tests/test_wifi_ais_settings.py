import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OWN = bytes.fromhex('020000000001')
AP = bytes.fromhex('020000000002')


class Station(C.Structure):
    _fields_ = [('peer', C.c_uint8*6), ('aid', C.c_uint16), ('listen', C.c_uint16),
                ('operational', C.c_uint16), ('basic', C.c_uint16),
                ('network', C.c_uint8), ('phy', C.c_uint8),
                ('state', C.c_uint8), ('rcpi', C.c_uint8)]


class BSS(C.Structure):
    _fields_ = [('own', C.c_uint8*6), ('ap', C.c_uint8*6), ('ssid', C.c_uint8*32),
                ('operational', C.c_uint16), ('basic', C.c_uint16),
                ('ssid_length', C.c_uint8), ('channel', C.c_uint8),
                ('connected', C.c_uint8), ('phy', C.c_uint8), ('enc_status', C.c_uint8),
                ('short_preamble', C.c_uint8), ('short_slot', C.c_uint8),
                ('erp_protection', C.c_uint8)]


class Settings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = pathlib.Path(cls.tmp.name)/'settings.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT/'include'), str(ROOT/'src/wifi_station.c'),
                        str(ROOT/'src/wifi_ais_bss.c'), '-o', str(lib)], check=True)
        cls.c = C.CDLL(str(lib))
        cls.c.wifi_station_pack.argtypes = [C.c_void_p, C.c_uint, C.POINTER(Station)]
        cls.c.wifi_ais_bss_pack.argtypes = [C.c_void_p, C.c_uint, C.POINTER(BSS)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def station(self):
        return Station((C.c_uint8*6)(*AP), 0x123, 3, 0x3fcf, 0x054f, 0, 3, 3, 137)

    def bss(self):
        c = BSS()
        c.own[:] = OWN; c.ap[:] = AP; c.ssid[:4] = b'test'
        c.operational = 0x3fcf; c.basic = 0x054f
        c.ssid_length = 4; c.channel = 6; c.connected = 1; c.phy = 3
        c.enc_status = 6; c.short_preamble = c.short_slot = c.erp_protection = 1
        return c

    def test_ais_station_entire_wire_packet(self):
        c = self.station(); out = C.create_string_buffer(48)
        self.assertEqual(self.c.wifi_station_pack(out, 48, C.byref(c)), 48)
        expected = bytearray(48)
        expected[9] = 0x41; expected[10:16] = AP
        expected[16:26] = bytes.fromhex('230103000003cf3f4f05')
        expected[28] = 3; expected[41:43] = bytes([137, 1])
        self.assertEqual(out.raw, bytes(expected))

    def test_legacy_p2p_and_preassociation_station_fields(self):
        c = self.station(); c.network = 1; c.aid = 1
        out = C.create_string_buffer(48)
        self.assertEqual(self.c.wifi_station_pack(out, 48, C.byref(c)), 48)
        self.assertEqual((out.raw[9], out.raw[20]), (0x22, 1))
        c.network = 0; c.state = 1; c.aid = 0
        self.assertEqual(self.c.wifi_station_pack(out, 48, C.byref(c)), 48)
        self.assertEqual((out.raw[9], out.raw[28], out.raw[42]), (0x41, 1, 0))

    def test_invalid_station_preserves_output(self):
        for field, value in [('network', 2), ('aid', 2008), ('aid', 0), ('listen', 0),
                             ('state', 0), ('state', 4), ('phy', 8),
                             ('operational', 0), ('basic', 0x8000)]:
            c = self.station(); setattr(c, field, value)
            out = C.create_string_buffer(b'X'*48, 48)
            self.assertEqual(self.c.wifi_station_pack(out, 48, C.byref(c)), 0)
            self.assertEqual(out.raw, b'X'*48)

    def test_ais_bss_entire_wire_packet(self):
        c = self.bss(); out = C.create_string_buffer(88)
        self.assertEqual(self.c.wifi_ais_bss_pack(out, 88, C.byref(c)), 88)
        expected = bytearray(88)
        expected[9] = 0; expected[11] = 4; expected[12:16] = b'test'
        expected[44:50] = AP; expected[52:56] = bytes.fromhex('cf3f4f05')
        expected[59:63] = bytes([1, 7, 6, 3]); expected[63:69] = OWN
        expected[73:75] = bytes([1, 6]); expected[76] = 1
        expected[85:88] = bytes([1, 1, 0x72])
        self.assertEqual(out.raw, bytes(expected))
        # Explicit enabled status does not imply this function installed a key.
        c.enc_status = 6; c.connected = 0
        self.assertEqual(self.c.wifi_ais_bss_pack(out, 88, C.byref(c)), 88)
        self.assertEqual((out.raw[9], out.raw[56], out.raw[61]), (1, 0xfe, 6))

    def test_invalid_bss_preserves_output(self):
        for field, value in [('ssid_length', 0), ('ssid_length', 33), ('channel', 0),
                             ('channel', 14), ('connected', 2), ('phy', 8),
                             ('enc_status', 1), ('enc_status', 7), ('short_preamble', 2), ('short_slot', 2),
                             ('erp_protection', 2), ('operational', 0), ('basic', 0),
                             ('basic', 0x8000)]:
            c = self.bss(); setattr(c, field, value)
            out = C.create_string_buffer(b'X'*88, 88)
            self.assertEqual(self.c.wifi_ais_bss_pack(out, 88, C.byref(c)), 0)
            self.assertEqual(out.raw, b'X'*88)

    def test_null_capacity_and_invalid_macs(self):
        for pack, factory, size in [(self.c.wifi_station_pack, self.station, 48),
                                    (self.c.wifi_ais_bss_pack, self.bss, 88)]:
            out = C.create_string_buffer(b'X'*size, size); c = factory()
            self.assertEqual(pack(out, size-1, C.byref(c)), 0)
            self.assertEqual(pack(out, size, None), 0)
            self.assertEqual(pack(None, size, C.byref(c)), 0)
            self.assertEqual(out.raw, b'X'*size)
        c = self.station(); c.peer[:] = bytes(6)
        self.assertEqual(self.c.wifi_station_pack(out, 88, C.byref(c)), 0)
        c = self.bss(); c.ap[:] = c.own[:]
        self.assertEqual(self.c.wifi_ais_bss_pack(out, 88, C.byref(c)), 0)

    def test_input_output_alias_supported(self):
        for pack, c, size, struct in [(self.c.wifi_station_pack, self.station(), 48, Station),
                                      (self.c.wifi_ais_bss_pack, self.bss(), 88, BSS)]:
            expected = C.create_string_buffer(size)
            self.assertEqual(pack(expected, size, C.byref(c)), size)
            aliased = C.create_string_buffer(size)
            C.memmove(aliased, C.byref(c), C.sizeof(c))
            self.assertEqual(pack(aliased, size, C.cast(aliased, C.POINTER(struct))), size)
            self.assertEqual(aliased.raw, expected.raw)


if __name__ == '__main__':
    unittest.main()
