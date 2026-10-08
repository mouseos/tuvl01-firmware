import ctypes,pathlib,struct,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
MAC=bytes.fromhex('000369071d22');PEER=bytes.fromhex('6c4ce20d50d4')
SERVER=bytes([192,168,74,1]);CLIENT=bytes([192,168,74,2]);BCAST=b'\xff'*6
def checksum(p):
    if len(p)%2:p+=b'\0'
    n=sum(struct.unpack('!'+str(len(p)//2)+'H',p))
    while n>>16:n=(n&65535)+(n>>16)
    return (~n)&65535
def ip(payload,proto=17,src=CLIENT,dst=SERVER,ethdst=MAC):
    h=bytearray(struct.pack('!BBHHHBBH4s4s',69,0,20+len(payload),0,0,64,proto,0,src,dst))
    h[10:12]=struct.pack('!H',checksum(bytes(h)))
    return ethdst+PEER+b'\x08\x00'+bytes(h)+payload
def udp(body,sport=12345,dport=4201,src=CLIENT,dst=SERVER):
    u=bytearray(struct.pack('!HHHH',sport,dport,len(body)+8,0)+body)
    c=checksum(src+dst+struct.pack('!BBH',0,17,len(u))+bytes(u))
    u[6:8]=struct.pack('!H',c or 65535);return bytes(u)
def dhcp(msg=1,options=b'',broadcast=True,ci=bytes(4)):
    b=bytearray(240);b[:3]=b'\x01\x01\x06';b[4:8]=b'\x12\x34\x56\x78'
    b[10]=128 if broadcast else 0;b[12:16]=ci;b[28:34]=PEER;b[236:240]=b'\x63\x82\x53\x63'
    return bytes(b)+bytes([53,1,msg])+options+b'\xff'
class Network(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();lib=pathlib.Path(cls.tmp.name)/'net.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(ROOT/'src/wifi_net.c'),'-o',str(lib)],check=True)
        cls.c=ctypes.CDLL(str(lib));cls.c.wifi_net_reply.restype=ctypes.c_uint
        cls.c.wifi_net_reply.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,
            ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def reply(self,p,capacity=1514):
        o=ctypes.create_string_buffer(1514)
        n=self.c.wifi_net_reply(p,len(p),MAC,PEER,o,capacity);return o.raw[:n]
    def dhcp_reply(self,b):
        return self.reply(ip(udp(b,68,67,bytes(4),b'\xff'*4),src=bytes(4),dst=b'\xff'*4,ethdst=BCAST))
    def verify_ip_udp(self,p):
        self.assertEqual(checksum(p[14:34]),0)
        n=struct.unpack('!H',p[38:40])[0]
        self.assertEqual(checksum(p[26:34]+struct.pack('!BBH',0,17,n)+p[34:34+n]),0)
    def test_dhcp_offer_ack_nak_and_destinations(self):
        offer=self.dhcp_reply(dhcp());self.assertEqual(len(offer),342)
        self.assertEqual(offer[:12],BCAST+MAC);self.assertEqual(offer[30:34],b'\xff'*4)
        self.assertEqual(offer[34:38],struct.pack('!HH',67,68));self.verify_ip_udp(offer)
        boot=offer[42:];self.assertEqual(boot[:3],b'\x02\x01\x06')
        self.assertEqual(boot[4:8],b'\x12\x34\x56\x78');self.assertEqual(boot[16:20],CLIENT)
        self.assertEqual(boot[240:249],bytes([53,1,2,54,4])+SERVER)
        request=dhcp(3,bytes([50,4])+CLIENT+bytes([54,4])+SERVER)
        ack=self.dhcp_reply(request);self.assertEqual(ack[284],5);self.verify_ip_udp(ack)
        nak=self.dhcp_reply(dhcp(3,b'\x32\x04\xc0\xa8\x08\xa3',False))
        self.assertEqual(nak[284],6);self.assertEqual(nak[:6],BCAST);self.assertEqual(nak[58:62],bytes(4))
        unicast=self.dhcp_reply(dhcp(broadcast=False));self.assertEqual(unicast[:6],PEER)
        self.assertEqual(unicast[30:34],CLIENT)
        renewal=self.dhcp_reply(dhcp(3,ci=CLIENT));self.assertEqual(renewal[284],5)
        self.assertEqual(renewal[30:34],CLIENT)
    def test_device_originated_udp(self):
        self.c.wifi_net_udp.restype=ctypes.c_uint
        self.c.wifi_net_udp.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint]
        body=b'TTS1'+bytes(range(16))*82;out=ctypes.create_string_buffer(1514)
        n=self.c.wifi_net_udp(body,len(body),4202,MAC,PEER,out,1514)
        packet=out.raw[:n];self.assertEqual(n,42+len(body));self.verify_ip_udp(packet)
        self.assertEqual(packet[:12],PEER+MAC);self.assertEqual(packet[42:],body)
        self.assertEqual(packet[34:38],struct.pack('!HH',4202,4202))
        self.assertEqual(self.c.wifi_net_udp(body,len(body),4202,MAC,PEER,out,41+len(body)),0)
        self.assertEqual(self.c.wifi_net_udp(body,1473,4202,MAC,PEER,out,1514),0)
    def test_dhcp_rejects_malformed_and_other_server(self):
        for b in [dhcp(3,bytes([54,4])+b'\xc0\xa8\x4a\x03'),dhcp(3),
                  dhcp(1,b'\x35\x01\x01'),dhcp(1,b'\x32\x05\x01'),
                  dhcp(1,b'\x34\x01\x01'),dhcp()[:-1]]:
            self.assertEqual(self.dhcp_reply(b),b'')
        b=bytearray(dhcp());b[28]^=1;self.assertEqual(self.dhcp_reply(bytes(b)),b'')
    def test_udp_echo_payload_and_checksums(self):
        data=bytes(range(256))+bytes(range(198));p=ip(udp(data))
        r=self.reply(p,496);self.assertEqual(len(r),496);self.assertEqual(r[42:],data)
        self.assertEqual(r[:12],PEER+MAC);self.assertEqual(r[26:34],SERVER+CLIENT)
        self.assertEqual(r[34:38],struct.pack('!HH',4201,12345));self.verify_ip_udp(r)
        self.assertEqual(self.reply(p,495),b'')
        bad=bytearray(p);bad[-1]^=1;self.assertEqual(self.reply(bytes(bad)),b'')
        self.assertEqual(self.reply(ip(udp(data,dport=4202))),b'')
    def test_icmp_echo(self):
        body=bytearray(b'\x08\0\0\0\x12\x34\x00\x01'+b'hello'*8)
        body[2:4]=struct.pack('!H',checksum(bytes(body)))
        p=ip(bytes(body),proto=1);r=self.reply(p)
        self.assertEqual(r[34],0);self.assertEqual(r[38:],p[38:])
        self.assertEqual(checksum(r[34:]),0);self.assertEqual(checksum(r[14:34]),0)
    def test_full_mtu_udp(self):
        for n in [1316,1472]:
            data=bytes(i%251 for i in range(n));p=ip(udp(data));r=self.reply(p)
            self.assertEqual(len(r),42+n);self.assertEqual(r[42:],data);self.verify_ip_udp(r)
            self.assertEqual(self.reply(p,len(p)-1),b'')
    def test_arp_and_wrong_peer(self):
        a=struct.pack('!HHBBH',1,0x800,6,4,1)+PEER+CLIENT+bytes(6)+SERVER
        p=BCAST+PEER+b'\x08\x06'+a;r=self.reply(p)
        self.assertEqual(len(r),42);self.assertEqual(r[20:22],b'\0\2')
        self.assertEqual(r[22:42],MAC+SERVER+PEER+CLIENT)
        bad=bytearray(p);bad[6]^=2;self.assertEqual(self.reply(bytes(bad)),b'')
        self.assertEqual(self.reply(p,41),b'')
    def test_ip_truncations_fragments_and_checksum(self):
        p=ip(udp(b'abc'))
        for n in range(len(p)):self.assertEqual(self.reply(p[:n]),b'')
        for pos in [14,16,20,24,29,38,40]:
            b=bytearray(p);b[pos]^=1;self.assertEqual(self.reply(bytes(b)),b'')
        b=bytearray(p);b[20]=0x20;b[24:26]=b'\0\0'
        b[24:26]=struct.pack('!H',checksum(bytes(b[14:34])))
        self.assertEqual(self.reply(bytes(b)),b'')
if __name__=='__main__':unittest.main()
