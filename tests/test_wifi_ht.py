"""Bounded peer IEs and20MHz HT/WMM wire consistency, independent of CPU endian."""
import ctypes as C,pathlib,struct,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Peer(C.Structure):
    _fields_=[('capability',C.c_uint16),('ampdu',C.c_uint8),('mcs',C.c_uint8),('present',C.c_uint8),('qos',C.c_uint8)]
class HT(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();lib=pathlib.Path(cls.tmp.name)/'ht.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/wifi_ht.c'),'-o',str(lib)],check=True)
        cls.lib=C.CDLL(str(lib))
        cls.lib.wifi_ht_parse.argtypes=[C.c_void_p,C.c_uint,C.POINTER(Peer)]
        cls.lib.wifi_ht_active.argtypes=[C.POINTER(Peer)]
        cls.lib.wifi_ht_ies.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint]
        cls.lib.wifi_ht_station.argtypes=[C.c_void_p,C.c_uint,C.POINTER(Peer)]
        cls.lib.wifi_beacon_pack.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint]
        cls.lib.wifi_ht_queues.argtypes=[C.c_void_p,C.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def request(self):
        ht=bytearray(26);ht[:4]=bytes.fromhex('6f011bff')
        return bytes([45,26])+ht+bytes.fromhex('dd070050f202000100')
    def test_valid_peer_and_empty_legacy(self):
        p=Peer();data=self.request();self.assertEqual(self.lib.wifi_ht_parse(data,len(data),C.byref(p)),1)
        self.assertEqual((p.capability,p.ampdu,p.mcs,p.present,p.qos),(0x16f,0x1b,255,1,1))
        self.assertTrue(self.lib.wifi_ht_active(C.byref(p)))
        self.assertEqual(self.lib.wifi_ht_parse(None,0,C.byref(p)),1);self.assertEqual(bytes(p),bytes(C.sizeof(p)))
    def test_truncated_duplicate_and_bad_vendor_leave_state(self):
        data=self.request();bad=[data[:n] for n in range(1,len(data)) if n!=28]
        bad += [data+data[:28],data+data[28:],bytes([45,25])+bytes(25),data[:-3]+bytes([2])+data[-2:]]
        for raw in bad:
            p=Peer(0xaaaa,1,2,3,4);before=bytes(p)
            self.assertEqual(self.lib.wifi_ht_parse(raw,len(raw),C.byref(p)),0,raw.hex());self.assertEqual(bytes(p),before)
        p=Peer();self.assertEqual(self.lib.wifi_ht_parse(None,1,C.byref(p)),0)
        self.assertEqual(self.lib.wifi_ht_parse(data,len(data),None),0)
    def test_wmm_and_mcs_required_for_ht(self):
        for qos,mcs,active in [(0,255,0),(1,0,0),(1,1,1),(1,255,1)]:
            p=Peer(12,0,mcs,1,qos);self.assertEqual(bool(self.lib.wifi_ht_active(C.byref(p))),bool(active))
    def test_advertise_20mhz_no_sgi_two_stream_or_uapsd(self):
        for channel in [1,6,13]:
            out=(C.c_uint8*90)(*([165]*90));n=self.lib.wifi_ht_ies(out,90,channel,1,1);self.assertEqual(n,78)
            b=bytes(out);self.assertEqual(b[:6],bytes.fromhex('2d1a0c0000ff'))
            self.assertEqual(b[6:15],bytes(9));self.assertEqual(b[15:18],bytes([65,0,1]))
            self.assertEqual(b[28:37],bytes([61,22,channel,0,3,0,0,0,1]))
            self.assertEqual(b[52:62],bytes.fromhex('dd180050f20201010000'));self.assertEqual(b[78:],bytes([165])*12)
    def test_advertisement_rejection_no_partial_output(self):
        for capacity,channel,ht,qos in [(77,1,1,1),(51,1,1,0),(25,1,0,1),(90,0,1,1),(90,14,1,1),(90,1,2,1)]:
            out=(C.c_uint8*90)(*([165]*90));self.assertEqual(self.lib.wifi_ht_ies(out,capacity,channel,ht,qos),0);self.assertEqual(bytes(out),bytes([165])*90)
    def test_station_preserves_identity_state_rates_rcpi(self):
        out=(C.c_uint8*48)(*range(48));before=bytes(out);p=Peer(0xffff,0x1b,0x7f,1,1)
        self.assertEqual(self.lib.wifi_ht_station(out,48,C.byref(p)),1);b=bytes(out)
        self.assertEqual(b[:21],before[:21]);self.assertEqual(b[22:26],before[22:26]);self.assertEqual(b[28],before[28]);self.assertEqual(b[41:],before[41:])
        self.assertEqual(b[21],before[21]|8);self.assertEqual(b[26:28],bytes([1,0]));self.assertEqual(b[29:34],bytes([127,0,27,12,0]));self.assertEqual(b[34:41],bytes(7))
        for cap in [0,47,49]:
            out=(C.c_uint8*48)(*range(48));self.assertEqual(self.lib.wifi_ht_station(out,cap,C.byref(p)),0);self.assertEqual(bytes(out),before)
    def test_beacon_transport_alignment_preserves_explicit_ie_length(self):
        for length,padded in [(36,52),(30,48),(114,132),(108,124),(255,272)]:
            ies=bytes(range(length));out=(C.c_uint8*280)(*([165]*280))
            self.assertEqual(self.lib.wifi_beacon_pack(out,280,ies,length),padded)
            b=bytes(out);self.assertEqual(b[14:16],bytes([length,0]));self.assertEqual(b[16:16+length],ies)
            self.assertEqual(b[16+length:padded],bytes(padded-16-length));self.assertEqual(b[padded:],bytes([165])*(280-padded));self.assertEqual(padded&3,0)
            out=(C.c_uint8*280)(*([165]*280));self.assertEqual(self.lib.wifi_beacon_pack(out,padded-1,ies,length),0);self.assertEqual(bytes(out),bytes([165])*280)
        out=(C.c_uint8*280)(*([165]*280));self.assertEqual(self.lib.wifi_beacon_pack(out,280,None,114),0);self.assertEqual(bytes(out),bytes([165])*280)
    def test_wmm_queue_matches_beacon_ac_parameters(self):
        out=(C.c_uint8*60)(*([165]*60));self.assertEqual(self.lib.wifi_ht_queues(out,60),52)
        ies=(C.c_uint8*78)();self.lib.wifi_ht_ies(ies,78,1,1,1);wmm=bytes(ies)[62:78]
        for ac in range(4):
            aifs,ecw,lo,hi=wmm[ac*4:ac*4+4]
            expected=((1<<(ecw&15))-1,(1<<(ecw>>4))-1,lo|(hi<<8),aifs&15)
            self.assertEqual(struct.unpack('<4H',bytes(out)[8+ac*10:16+ac*10]),expected)
        self.assertEqual(bytes(out)[48:52],bytes([1,1,0,0]));self.assertEqual(bytes(out)[52:],bytes([165])*8)
if __name__=='__main__':unittest.main()
