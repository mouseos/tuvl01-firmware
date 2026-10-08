import ctypes,pathlib,struct,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Query(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();path=pathlib.Path(cls.tmp.name)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
                        str(ROOT/'src/wifi_fw_query.c'),'-o',str(path/'query.so')],check=True)
        cls.lib=ctypes.CDLL(str(path/'query.so'))
        cls.lib.wifi_compile_query.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
        cls.lib.wifi_compile_decode.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint8,ctypes.c_uint,ctypes.POINTER(ctypes.c_uint32)]
        cls.lib.wifi_station_query.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p]
        cls.lib.wifi_rate_mailbox_query.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
        cls.lib.wifi_rate_mailbox_decode.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint8,ctypes.c_uint,ctypes.POINTER(ctypes.c_uint32)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_rate_mailbox_query_is_fixed_read_only_and_bounded(self):
        for index in (0,1):
            out=(ctypes.c_uint8*20)(*([0xa5]*20))
            self.assertEqual(self.lib.wifi_rate_mailbox_query(out,20,index),16)
            self.assertEqual(bytes(out[:16]),bytes(8)+struct.pack('<II',0x90000100+index*4,0))
            self.assertEqual(bytes(out[16:]),b'\xa5'*4)
        for cap,index in ((15,0),(16,2)):
            out=(ctypes.c_uint8*20)(*([0xa5]*20))
            self.assertEqual(self.lib.wifi_rate_mailbox_query(out,cap,index),0)
            self.assertEqual(bytes(out),b'\xa5'*20)
        self.assertEqual(self.lib.wifi_rate_mailbox_query(None,16,0),0)
    def test_rate_mailbox_matches_all_response_identity_fields(self):
        for index in (0,1):
            p=struct.pack('<HHBBHII',16,1,10,255,0,0x90000100+index*4,0xffffffff)
            value=ctypes.c_uint32(0x12345678)
            self.assertEqual(self.lib.wifi_rate_mailbox_decode(p,16,255,index,ctypes.byref(value)),1)
            self.assertEqual(value.value,0xffffffff)
            for offset in (0,2,4,5,8,9,10,11):
                corrupt=bytearray(p);corrupt[offset]^=1;value.value=0x12345678
                self.assertEqual(self.lib.wifi_rate_mailbox_decode(bytes(corrupt),16,255,index,ctypes.byref(value)),0)
                self.assertEqual(value.value,0x12345678)
    def test_rate_mailbox_rejects_short_extended_and_invalid_index(self):
        p=struct.pack('<HHBBHII',16,1,10,7,0,0x90000100,0)
        value=ctypes.c_uint32(123)
        for length,index in ((15,0),(17,0),(16,2)):
            self.assertEqual(self.lib.wifi_rate_mailbox_decode(p+bytes(4),length,7,index,ctypes.byref(value)),0)
            self.assertEqual(value.value,123)
        self.assertEqual(self.lib.wifi_rate_mailbox_decode(None,16,7,0,ctypes.byref(value)),0)
        self.assertEqual(self.lib.wifi_rate_mailbox_decode(p,16,7,0,None),0)
    def test_compile_queries_have_zero_data_and_little_endian_id(self):
        for index in range(2):
            out=(ctypes.c_uint8*280)(*([0xa5]*280))
            self.assertEqual(self.lib.wifi_compile_query(out,280,index),272)
            self.assertEqual(bytes(out[:272]),b'\0'*8+struct.pack('<II',0xa0240000|index,0)+b'\0'*256)
            self.assertEqual(bytes(out[272:]),b'\xa5'*8)
    def test_station_query_uses_index_zero_peer_and_read_clear_zero(self):
        out=(ctypes.c_uint8*40)(*([0xa5]*40));peer=b'\x02\x03\x04\x05\x06\x07'
        self.assertEqual(self.lib.wifi_station_query(out,40,peer),36)
        self.assertEqual(bytes(out[:36]),b'\0'*12+peer+b'\0'*18)
        self.assertEqual(bytes(out[36:]),b'\xa5'*4)
    def test_reject_bad_query_bounds_and_null_without_output(self):
        out=(ctypes.c_uint8*280)(*([0xa5]*280))
        for capacity,index in ((271,0),(280,2)):
            self.assertEqual(self.lib.wifi_compile_query(out,capacity,index),0)
        self.assertEqual(self.lib.wifi_compile_query(None,40,0),0)
        self.assertEqual(self.lib.wifi_station_query(out,35,b'abcdef'),0)
        self.assertEqual(self.lib.wifi_station_query(out,40,None),0)
        self.assertEqual(self.lib.wifi_station_query(None,40,b'abcdef'),0)
        self.assertEqual(bytes(out),b'\xa5'*280)
    def test_compile_response_identity_and_flag_endian(self):
        packet=bytearray(struct.pack('<HHBBBBII',16,1,0x1f,255,0,0,0xa0240000,0x12345679))
        out=ctypes.c_uint32(0xa5a5a5a5)
        self.assertEqual(self.lib.wifi_compile_decode(bytes(packet),16,255,0,ctypes.byref(out)),1)
        self.assertEqual(out.value,0x12345679)
        full=packet+bytearray(256);struct.pack_into('<H',full,0,len(full))
        self.assertEqual(self.lib.wifi_compile_decode(bytes(full),len(full),255,0,ctypes.byref(out)),1)
        self.assertEqual(out.value,0x12345679)
        cases=[packet[:n] for n in (0,7,15)]+[packet+b'\0']
        for offset in (0,2,3,4,5,8,10,11):
            p=packet.copy();p[offset]^=1;cases.append(p)
        for p in cases:
            out.value=0xa5a5a5a5
            self.assertEqual(self.lib.wifi_compile_decode(bytes(p),len(p),255,0,ctypes.byref(out)),0)
            self.assertEqual(out.value,0xa5a5a5a5)
        self.assertEqual(self.lib.wifi_compile_decode(None,16,255,0,ctypes.byref(out)),0)
        self.assertEqual(self.lib.wifi_compile_decode(bytes(packet),16,255,0,None),0)
        self.assertEqual(self.lib.wifi_compile_decode(bytes(packet),16,255,2,ctypes.byref(out)),0)
if __name__=='__main__':unittest.main()
