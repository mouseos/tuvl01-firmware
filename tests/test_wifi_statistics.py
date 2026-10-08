import ctypes, pathlib, struct, subprocess, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]

class Counter(ctypes.Structure):
    _fields_ = [('low', ctypes.c_uint32), ('high', ctypes.c_uint32)]

class Statistics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        library = pathlib.Path(cls.tmp.name) / 'statistics.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT/'include'), str(ROOT/'src/wifi_statistics.c'),
                        '-o', str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.wifi_statistics_decode.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                                   ctypes.c_uint8, ctypes.POINTER(Counter)]
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
    def packet(self):
        values = [0, 0xffffffffffffffff, 0x123456789abcdef0] + [1 << n for n in range(32, 41)]
        return bytearray(struct.pack('<HHBBBB', 104, 1, 6, 255, 0, 0) +
                         struct.pack('<12Q', *values)), values
    def decode(self, packet, sequence=255):
        output = (Counter * 12)()
        for c in output: c.low, c.high = 123, 456
        result = self.lib.wifi_statistics_decode(bytes(packet), len(packet), sequence, output)
        return result, [(c.high << 32) | c.low for c in output]
    def test_full_64_bit_little_endian_counters(self):
        packet, values = self.packet()
        self.assertEqual(self.decode(packet), (1, values))
    def test_reject_wrong_sequence_event_type_and_length_without_output(self):
        packet, _ = self.packet()
        cases = [packet[:n] for n in (0, 7, 8, 103)]
        for offset in (0, 2, 3, 4, 5):
            altered = packet.copy(); altered[offset] ^= 1; cases.append(altered)
        for malformed in cases:
            result, values = self.decode(malformed)
            self.assertEqual(result, 0)
            self.assertEqual(values, [(456 << 32) | 123] * 12)

if __name__ == '__main__': unittest.main()
