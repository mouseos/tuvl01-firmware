"""Parse actual-C aggregate output as independent Ethernet/IP/UDP/TTS1 frames."""
import ctypes,pathlib,struct,subprocess,tempfile,unittest
from test_wifi_net import MAC,PEER,checksum
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Aggregate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();lib=pathlib.Path(cls.tmp.name)/'pack.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(ROOT/'src/wifi_ts_tx.c'),
            str(ROOT/'src/wifi_net.c'),'-o',str(lib)],check=True)
        cls.c=ctypes.CDLL(str(lib));cls.pack=cls.c.wifi_ts_tx_pack
        cls.pack.restype=ctypes.c_uint
        cls.pack.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint,
            ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_all_packet_counts_roundtrip_and_termination(self):
        for count in range(1,15):
            with self.subTest(count=count):
                data=bytes((i*13+5)&255 for i in range(count*188))
                out=ctypes.create_string_buffer(b'\xa5'*4096,4096)
                length=self.pack(data,count,0xffffffff,100,1,MAC,PEER,out,3072)
                self.assertGreater(length,0);self.assertEqual(length%512,0)
                self.assertLessEqual(length,3072)
                frames=[];position=0;payload=bytearray();index=100
                while out.raw[position:position+4]!=bytes(4):
                    logical=int.from_bytes(out.raw[position:position+2],'little')
                    hif=out.raw[position:position+16]
                    self.assertEqual(hif[2:6],bytes([14,4,14,16]))
                    final_frame=len(frames)+1==(count+6)//7
                    self.assertEqual(hif[10:16],bytes([0,32 if final_frame else 0,0,0,0,0]))
                    frame=out.raw[position+16:position+logical]
                    self.assertEqual(frame[:12],PEER+MAC)
                    self.assertEqual(checksum(frame[14:34]),0)
                    udp=frame[34:];self.assertEqual(struct.unpack('!H',udp[2:4])[0],4202)
                    self.assertEqual(checksum(frame[26:34]+struct.pack('!BBH',0,17,len(udp))+udp),0)
                    body=udp[8:];self.assertEqual(body[:4],b'TTS1')
                    seq,idx,flags=struct.unpack('!III',body[4:16])
                    self.assertEqual(seq,(0xffffffff+len(frames))&0xffffffff)
                    self.assertEqual(idx,index);self.assertEqual(flags,1 if not frames else 0)
                    n=(len(body)-16)//188;self.assertGreater(n,0);self.assertLessEqual(n,7)
                    payload+=body[16:];index+=n;frames.append(frame)
                    aligned=(logical+3)&~3
                    self.assertEqual(out.raw[position+logical:position+aligned],bytes(aligned-logical))
                    position+=aligned
                self.assertEqual(len(frames),(count+6)//7)
                self.assertEqual(payload,data)
                self.assertEqual(out.raw[position:length],bytes(length-position))
                self.assertEqual(out.raw[length:],b'\xa5'*(4096-length))
    def test_more_data_only_marks_a_real_following_same_peer_frame(self):
        pack=self.c.wifi_ts_tx_pack_forwarding;pack.restype=ctypes.c_uint
        pack.argtypes=self.pack.argtypes+[ctypes.c_uint]
        data=bytes((i*13+5)&255 for i in range(14*188))
        for count in range(1,15):
            legacy=ctypes.create_string_buffer(4096);marked=ctypes.create_string_buffer(4096)
            n=self.pack(data,count,10,20,1,MAC,PEER,legacy,3072)
            self.assertEqual(pack(data,count,10,20,1,MAC,PEER,marked,3072,1),n)
            expected=bytearray(legacy.raw)
            if count>7:expected[11]=3
            self.assertEqual(marked.raw,bytes(expected))
            first_length=int.from_bytes(marked.raw[:2],'little')
            final=(first_length+3)&~3 if count>7 else 0
            self.assertEqual(marked.raw[final+11],0x20)
        untouched=ctypes.create_string_buffer(b'\xa5'*4096,4096)
        self.assertEqual(pack(data,14,0,0,0,MAC,PEER,untouched,3072,2),0)
        self.assertEqual(untouched.raw,b'\xa5'*4096)
    def test_invalid_capacity_and_count_leave_output_untouched(self):
        for count,capacity in [(0,3072),(15,3072),(14,3071),(7,1535),(1,511)]:
            out=ctypes.create_string_buffer(b'\xa5'*4096,4096)
            self.assertEqual(self.pack(bytes(14*188),count,0,0,0,MAC,PEER,out,capacity),0)
            self.assertEqual(out.raw,b'\xa5'*4096)
if __name__=='__main__':unittest.main()
