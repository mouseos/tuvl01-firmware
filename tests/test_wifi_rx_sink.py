import ctypes,pathlib,struct,subprocess,tempfile,unittest
from test_wifi_net import MAC,PEER,ip,udp,checksum
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Stats(ctypes.Structure):
    _fields_=[(k,ctypes.c_uint32) for k in
        ('packets','bytes','missing','reordered','invalid','next_sequence',
         'first_tick','last_tick','max_gap_ticks','overflow')]
def body(seq,n=1316):
    return b'TWR1'+struct.pack('!II',seq,n)+bytes((i+seq%251)%251 for i in range(12,n))
def frame(seq=0,n=1316):
    return ip(udp(body(seq,n),dport=4203))
class Sink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();lib=pathlib.Path(cls.tmp.name)/'sink.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(ROOT/'src/wifi_rx_sink.c'),'-o',str(lib)],check=True)
        cls.c=ctypes.CDLL(str(lib));cls.c.wifi_rx_sink_receive.restype=ctypes.c_int
        cls.c.wifi_rx_sink_receive.argtypes=[ctypes.POINTER(Stats),ctypes.c_void_p,
            ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def call(self,s,p,tick=100):
        return self.c.wifi_rx_sink_receive(ctypes.byref(s),p,len(p),MAC,PEER,tick)
    def test_sequence_gaps_duplicates_timing_and_payload_bytes(self):
        s=Stats()
        for seq,tick in [(0,100),(2,110),(1,111),(2,115),(3,130)]:
            self.assertEqual(self.call(s,frame(seq),tick),1)
        self.assertEqual((s.packets,s.bytes,s.missing,s.reordered,s.invalid),(3,3948,1,2,0))
        self.assertEqual((s.first_tick,s.last_tick,s.max_gap_ticks),(100,130,20))
    def test_first_missing_and_tick_wrap(self):
        s=Stats();self.call(s,frame(3),0xfffffff0);self.call(s,frame(4),10)
        self.assertEqual((s.missing,s.packets,s.max_gap_ticks),(3,2,26))
    def test_invalid_bodies_are_consumed_without_advancing_sequence(self):
        s=Stats()
        data=bytearray(body(0));data[-1]^=1
        for b in (b'',b'TWR1',bytes(data),body(0)[:8]+struct.pack('!I',1)+body(0)[12:],body(0xffffffff)):
            self.assertEqual(self.call(s,ip(udp(b,dport=4203))),1)
        self.assertEqual((s.invalid,s.packets,s.bytes,s.next_sequence),(5,0,0,0))
        self.assertEqual(self.call(s,frame()),1);self.assertEqual(s.packets,1)
    def test_truncations_checksum_fragments_and_wrong_addresses_do_not_change_stats(self):
        p=frame();s=Stats();original=bytes(s)
        for n in range(len(p)):
            self.assertEqual(self.call(s,p[:n]),0);self.assertEqual(bytes(s),original)
        for pos in (0,6,12,14,24,29,33,36,38,40,100):
            q=bytearray(p);q[pos]^=1
            self.assertEqual(self.call(s,bytes(q)),0);self.assertEqual(bytes(s),original)
        for flags in (0x2000,1,0x8000):
            q=bytearray(p);q[20:22]=struct.pack('!H',flags);q[24:26]=b'\0\0'
            q[24:26]=struct.pack('!H',checksum(bytes(q[14:34])))
            self.assertEqual(self.call(s,bytes(q)),0)
        self.assertEqual(self.call(s,ip(udp(body(0),dport=4201))),0)
    def test_zero_checksum_padding_unaligned_and_max_mtu(self):
        s=Stats();p=bytearray(frame(n=1472));p[40:42]=b'\0\0'
        padded=bytes(p)+b'\xff'*8
        storage=ctypes.create_string_buffer(b'!'+padded)
        self.assertEqual(self.c.wifi_rx_sink_receive(ctypes.byref(s),
            ctypes.byref(storage,1),len(padded),MAC,PEER,123),1)
        self.assertEqual((s.packets,s.bytes),(1,1472))
    def test_saturation_is_reported_not_silently_wrapped(self):
        s=Stats();s.bytes=0xfffffff0
        self.call(s,frame());self.assertEqual((s.bytes,s.overflow),(0xffffffff,1))
        s.invalid=0xffffffff;self.call(s,ip(udp(b'bad',dport=4203)))
        self.assertEqual((s.invalid,s.overflow),(0xffffffff,1))
if __name__=='__main__':unittest.main()
