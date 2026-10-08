import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
MAC=bytes.fromhex('000369071d22')
PEER=bytes.fromhex('020102030405')
class Management(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        lib=pathlib.Path(cls.tmp.name)/'mgmt.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(ROOT/'src/wifi_mgmt.c'),str(ROOT/'src/wifi_rates.c'),'-o',str(lib)],check=True)
        cls.c=ctypes.CDLL(str(lib))
        cls.c.wifi_mgmt_reply.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,
            ctypes.c_uint16,ctypes.c_void_p,ctypes.c_uint]
        cls.c.wifi_mgmt_reply.restype=ctypes.c_uint
        cls.c.wifi_assoc_reply.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,
            ctypes.c_void_p,ctypes.c_uint16,ctypes.c_void_p,ctypes.c_uint,
            ctypes.POINTER(ctypes.c_uint16),ctypes.POINTER(ctypes.c_uint16)]
        cls.c.wifi_assoc_reply.restype=ctypes.c_uint
        cls.c.wifi_mgmt_reply_profile.argtypes=cls.c.wifi_mgmt_reply.argtypes+[ctypes.c_uint]
        cls.c.wifi_mgmt_reply_profile.restype=ctypes.c_uint
        cls.c.wifi_assoc_reply_profile.argtypes=cls.c.wifi_assoc_reply.argtypes+[ctypes.c_uint]
        cls.c.wifi_assoc_reply_profile.restype=ctypes.c_uint
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def request(self,subtype,body):
        return bytes([subtype,0,0,0])+MAC+PEER+MAC+bytes(2)+body
    def reply(self,p,cap=128):
        out=ctypes.create_string_buffer(128)
        n=self.c.wifi_mgmt_reply(p,len(p),MAC,0xabc,out,cap)
        return out.raw[:n]
    def test_open_auth_and_addresses(self):
        p=self.request(0xb0,b'\0\0\1\0\0\0');r=self.reply(p)
        self.assertEqual(len(r),30)
        self.assertEqual(r[4:22],PEER+MAC+MAC)
        self.assertEqual(r[22:24],bytes.fromhex('c0ab'))
        self.assertEqual(r[24:],b'\0\0\2\0\0\0')
        self.assertEqual(self.reply(p,29),b'')
        for n in range(len(p)):self.assertEqual(self.reply(p[:n]),b'')
    def test_probe_ssid_filter_and_bounds(self):
        p=self.request(0x40,b'\0\6TUVL01')
        r=self.reply(p)
        self.assertEqual(r[0],0x50);self.assertEqual(r[32:36],b'\x64\0\1\4')
        self.assertEqual(r[36:44],b'\0\6TUVL01')
        self.assertTrue(self.reply(self.request(0x40,b'\0\0')))
        for body in [b'',b'\0',b'\0\7TUVL01',b'\0\6OTHER!',b'\0\0\0\0']:
            self.assertEqual(self.reply(self.request(0x40,body)),b'')
    def test_reject_unrelated_or_invalid_frames(self):
        p=self.request(0xb0,b'\0\0\1\0\0\0')
        for offset,value in [(0,0x80),(1,0x40),(1,4),(4,2),(10,1),(16,2),
                             (22,1),(24,1),(26,2),(28,1)]:
            bad=bytearray(p);bad[offset]=value
            self.assertEqual(self.reply(bytes(bad)),b'')
        self.assertEqual(self.reply(p+b'\0'),b'')
    def assoc_request(self):
        return self.request(0,b'\x01\x04\x03\x00'+b'\0\6TUVL01'+
            bytes.fromhex('010882848b968c1298243204b048606c'))
    def assoc_reply(self,p,peer=PEER,capacity=128):
        out=ctypes.create_string_buffer(128)
        rates=ctypes.c_uint16();listen=ctypes.c_uint16()
        n=self.c.wifi_assoc_reply(p,len(p),MAC,peer,0xabc,out,capacity,
            ctypes.byref(rates),ctypes.byref(listen))
        return out.raw[:n],rates.value,listen.value
    def test_association_and_negotiated_parameters(self):
        r,rates,listen=self.assoc_reply(self.assoc_request())
        self.assertEqual(r[0],0x10);self.assertEqual(len(r),46)
        self.assertEqual(r[4:22],PEER+MAC+MAC)
        self.assertEqual(r[24:30],bytes.fromhex('0104000001c0'))
        self.assertEqual((rates,listen),(0x3fcf,3))
        self.assertEqual(self.assoc_reply(self.assoc_request(),capacity=45)[0],b'')
    def test_association_rejects_wrong_peer_and_bad_ies(self):
        p=self.assoc_request()
        for peer in [bytes(6),bytes.fromhex('020102030406')]:
            self.assertEqual(self.assoc_reply(p,peer=peer)[0],b'')
        for offset,value in [(0,0x20),(1,0x40),(4,2),(22,1),(24,0x11),
                             (26,0),(30,ord('X')),(41,0xff),(48,0x7f)]:
            bad=bytearray(p);bad[offset]=value
            self.assertEqual(self.assoc_reply(bytes(bad))[0],b'',(offset,value))
        for body in [p[:-1],p+b'\0',p+b'\0\0',p+b'\1\1\x82']:
            self.assertEqual(self.assoc_reply(body)[0],b'')
    def test_erp_probe_and_association_agree_and_negotiate_only_erp(self):
        ies=bytes.fromhex('01088c129824b048606c')
        out=ctypes.create_string_buffer(128);rates=ctypes.c_uint16();listen=ctypes.c_uint16()
        probe=self.request(0x40,b'\0\6TUVL01')
        n=self.c.wifi_mgmt_reply_profile(probe,len(probe),MAC,1,out,128,1)
        self.assertEqual(out.raw[36:n],b'\0\6TUVL01'+ies+bytes.fromhex('0301012a0100'))
        for p in (self.assoc_request(),self.request(0,b'\x01\x04\x03\0'+b'\0\6TUVL01'+ies)):
            n=self.c.wifi_assoc_reply_profile(p,len(p),MAC,PEER,1,out,128,ctypes.byref(rates),ctypes.byref(listen),1)
            self.assertEqual(n,40);self.assertEqual(out.raw[30:n],ies)
            self.assertEqual((rates.value,listen.value),(0x3fc0,3))
    def test_erp_missing_basic_or_invalid_profile_preserves_outputs(self):
        good=self.request(0,b'\x01\x04\x03\0'+b'\0\6TUVL01'+bytes.fromhex('01088c129824b048606c'))
        missing=good.replace(bytes.fromhex('b048'),bytes.fromhex('6048'))
        for p,capacity,profile in ((missing,128,1),(good,39,1),(good,128,2)):
            out=ctypes.create_string_buffer(b'X'*128);rates=ctypes.c_uint16(99);listen=ctypes.c_uint16(77)
            self.assertEqual(self.c.wifi_assoc_reply_profile(p,len(p),MAC,PEER,1,out,capacity,ctypes.byref(rates),ctypes.byref(listen),profile),0)
            self.assertEqual(out.raw[:128],b'X'*128);self.assertEqual((rates.value,listen.value),(99,77))
