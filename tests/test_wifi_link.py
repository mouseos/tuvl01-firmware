import ctypes,pathlib,struct,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Entry(ctypes.Structure):
    _fields_=[('rssi',ctypes.c_int),('quality_raw',ctypes.c_uint),('speed_raw',ctypes.c_uint),
              ('busy_raw',ctypes.c_uint),('ready',ctypes.c_uint)]
class Quality(ctypes.Structure):
    _fields_=[('count',ctypes.c_uint),('ready_known',ctypes.c_uint),('entry',Entry*2)]
class Link(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();library=pathlib.Path(cls.tmp.name)/'link.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(ROOT/'src/wifi_link.c'),'-o',str(library)],check=True)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.wifi_link_decode.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint8,ctypes.POINTER(Quality)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def packet(self,body):return bytearray(struct.pack('<HHBBBB',8+len(body),1,5,255,0,0)+body)
    def decode(self,packet):
        output=Quality();ctypes.memset(ctypes.byref(output),0xa5,ctypes.sizeof(output))
        result=self.lib.wifi_link_decode(bytes(packet),len(packet),255,ctypes.byref(output))
        return result,output
    def test_legacy_signed_rssi_little_endian_speed_and_unknown_readiness(self):
        result,output=self.decode(self.packet(bytes([216,201,0x34,0x12,255,255])))
        self.assertEqual((result,output.count,output.ready_known),(1,1,0))
        e=output.entry[0]
        self.assertEqual((e.rssi,e.quality_raw,e.speed_raw,e.busy_raw,e.ready),(-40,201,0x1234,255,0))
    def test_extended_preserves_unready_network_data_without_claiming_ready(self):
        result,output=self.decode(self.packet(bytes([128,0,108,0,50,1,127,255,1,2,0,0])))
        self.assertEqual((result,output.count,output.ready_known),(1,2,1))
        self.assertEqual((output.entry[0].rssi,output.entry[0].speed_raw,output.entry[0].ready),(-128,108,1))
        self.assertEqual((output.entry[1].rssi,output.entry[1].speed_raw,output.entry[1].ready),(127,513,0))
    def test_malformed_identity_layout_or_flags_leave_output_untouched(self):
        packet=self.packet(bytes([216,0,108,0,0,1]*2))
        cases=[packet[:n] for n in (0,7,13,14,16,19)]
        for offset in (0,2,3,4,5,13,19):
            altered=packet.copy();altered[offset]^=3;cases.append(altered)
        for malformed in cases:
            result,output=self.decode(malformed)
            self.assertEqual(result,0)
            self.assertEqual(bytes(output),bytes([0xa5])*ctypes.sizeof(output))
if __name__=='__main__':unittest.main()
