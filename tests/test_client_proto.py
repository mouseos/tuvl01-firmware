"""Portable client protocol layer (client/tuvl01_proto.c) against the documented wire format."""
import ctypes,pathlib,struct,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Reply(ctypes.Structure):
    _fields_=[('op',ctypes.c_uint8),('status',ctypes.c_uint8),('state',ctypes.c_uint8),('id',ctypes.c_uint16),
              ('version',ctypes.c_uint8),('revision',ctypes.c_uint16),('stream_port',ctypes.c_uint16),
              ('caps',ctypes.c_uint32),('channel',ctypes.c_uint16)]
class Stream(ctypes.Structure):
    _fields_=[('sequence',ctypes.c_uint32),('index',ctypes.c_uint32),('flags',ctypes.c_uint32),
              ('ts',ctypes.c_void_p),('packets',ctypes.c_size_t)]
class Loss(ctypes.Structure):
    _fields_=[('expected',ctypes.c_uint32),('started',ctypes.c_int),('datagrams',ctypes.c_uint64),
              ('missing',ctypes.c_uint64),('resyncs',ctypes.c_uint64),('reordered',ctypes.c_uint64),('invalid',ctypes.c_uint64)]
def datagram(seq,index=0,flags=0,packets=7):
    return b'TTS1'+struct.pack('!III',seq,index,flags)+(b'\x47'+bytes(187))*packets
class ClientProto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();lib=pathlib.Path(cls.tmp.name)/'proto.so'
        subprocess.run(['cc','-shared','-fPIC','-std=c99','-Wall','-Wextra','-Werror',
            str(ROOT/'client/tuvl01_proto.c'),'-o',str(lib)],check=True)
        c=cls.c=ctypes.CDLL(str(lib))
        c.tuvl01_parse_reply.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.POINTER(Reply)]
        c.tuvl01_parse_stream.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.POINTER(Stream)]
        c.tuvl01_loss_init.argtypes=[ctypes.POINTER(Loss)]
        c.tuvl01_loss_update.argtypes=[ctypes.POINTER(Loss),ctypes.POINTER(Stream)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def reply(self,raw):
        r=Reply();rc=self.c.tuvl01_parse_reply(raw,len(raw),ctypes.byref(r));return rc,r
    def test_request_layout(self):
        out=ctypes.create_string_buffer(8)
        self.assertEqual(self.c.tuvl01_build_request(out,2,0xabcd),8)
        self.assertEqual(out.raw,b'TCT1\x02\x00\xab\xcd')
    def test_hello_reply_captured_from_device(self):
        rc,r=self.reply(bytes.fromhex('544354318100000101'+'00a7'+'00000001'+'106a'+'00'))
        self.assertEqual(rc,0);self.assertEqual((r.op,r.status,r.id,r.version,r.revision,r.caps,r.stream_port,r.state),
            (1,0,1,1,167,1,4202,0))
    def test_status_and_simple_replies(self):
        rc,r=self.reply(bytes.fromhex('544354318400000401000000'));self.assertEqual((rc,r.op,r.state,r.channel),(0,4,1,0))
        rc,r=self.reply(bytes.fromhex('544354318200000202'));self.assertEqual((rc,r.op,r.state),(0,2,2))
    def test_error_status_and_invalid_replies(self):
        rc,r=self.reply(bytes.fromhex('54435431d502007700'));self.assertEqual((rc,r.status,r.op),(0,2,0x55))
        for bad in (b'',b'TCT1',b'TCT1\x01\x00\x00\x01\x00',b'XXXX\x81\x00\x00\x01\x00',
                    bytes.fromhex('5443543181000001010000')):  # truncated HELLO
            self.assertLess(self.reply(bad)[0],0)
    def test_stream_datagram(self):
        s=Stream();d=datagram(5,70,1,3)
        self.assertEqual(self.c.tuvl01_parse_stream(d,len(d),ctypes.byref(s)),0)
        self.assertEqual((s.sequence,s.index,s.flags,s.packets),(5,70,1,3))
        self.assertEqual(ctypes.string_at(s.ts,188*3),d[16:])
        for bad in (b'',d[:-1],b'TTS2'+d[4:],d[:12]+struct.pack('!I',2)+d[16:],datagram(0,0,0,8)):
            self.assertLess(self.c.tuvl01_parse_stream(bad,len(bad),ctypes.byref(Stream())),0)
    def test_loss_accounting_including_wraparound_and_reorder(self):
        l=Loss();self.c.tuvl01_loss_init(ctypes.byref(l))
        def feed(seq,flags=0):
            s=Stream();d=datagram(seq,0,flags);self.c.tuvl01_parse_stream(d,len(d),ctypes.byref(s))
            return self.c.tuvl01_loss_update(ctypes.byref(l),ctypes.byref(s))
        self.assertEqual(feed(0xfffffffe),0);self.assertEqual(feed(0xffffffff),0);self.assertEqual(feed(0),0)
        self.assertEqual(l.missing,0)
        self.assertEqual(feed(4,1),0);self.assertEqual((l.missing,l.resyncs),(3,1))
        self.assertEqual(feed(3),1);self.assertEqual(l.reordered,1)       # late duplicate dropped
        self.assertEqual(feed(5),0);self.assertEqual((l.missing,l.datagrams),(3,5))
if __name__=='__main__':unittest.main()
