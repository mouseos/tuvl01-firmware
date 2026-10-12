"""Wi-Fi control service (UDP 4200): protocol, stream ownership and client watchdog."""
import ctypes,pathlib,struct,subprocess,tempfile,unittest
from test_wifi_net import MAC,PEER,CLIENT,SERVER,ip,udp,checksum
ROOT=pathlib.Path(__file__).resolve().parents[1]
STUB='''
#include <stdint.h>
#include "wifi_net.h"
#include "wifi_ctl.h"
int stub_active;
int tuner_ts_stream_active(void){return stub_active;}
void setup(void){wifi_net_service=wifi_ctl_service;}
void teardown(void){wifi_net_service=0;}
'''
def request(op,ident=0x1234,payload=b''):return b'TCT1'+bytes([op,0])+struct.pack('!H',ident)+payload
class Control(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name);(p/'stub.c').write_text(STUB)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
            str(p/'stub.c'),str(ROOT/'src/wifi_net.c'),str(ROOT/'src/wifi_ctl.c'),'-o',str(p/'ctl.so')],check=True)
        c=cls.c=ctypes.CDLL(str(p/'ctl.so'))
        c.wifi_net_reply.restype=ctypes.c_uint
        c.wifi_net_reply.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint]
        c.wifi_ctl_poll.restype=ctypes.c_int;c.wifi_ctl_poll.argtypes=[ctypes.c_uint,ctypes.c_uint]
        cls.active=ctypes.c_int.in_dll(c,'stub_active')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.c.setup();self.active.value=0
        while self.c.wifi_ctl_poll(0,0)>=0:pass  # drain any pending command
        self.c.wifi_ctl_poll(0,10**9)
    def send(self,body,dport=4200,sport=40000):
        p=ip(udp(body,sport,dport));o=ctypes.create_string_buffer(1514)
        n=self.c.wifi_net_reply(p,len(p),MAC,PEER,o,1514);return o.raw[:n]
    def test_hello(self):
        r=self.send(request(1,0xbeef,b''),sport=40001)
        self.assertEqual(checksum(r[14:34]),0)
        sport,dport,length=struct.unpack('!HHH',r[34:40])
        self.assertEqual((sport,dport),(4200,40001));self.assertEqual(length,len(r)-34)
        n=struct.unpack('!H',r[38:40])[0]
        self.assertEqual(checksum(r[26:34]+struct.pack('!BBH',0,17,n)+r[34:34+n]),0)
        body=r[42:];self.assertEqual(body[:4],b'TCT1');self.assertEqual(body[4],0x81);self.assertEqual(body[5],0)
        self.assertEqual(body[6:8],b'\xbe\xef')
        version,rev,caps,port,state=struct.unpack('!BHIHB',body[8:18])
        self.assertEqual((version,rev,caps,port,state),(1,167,1,4202,0))
    def test_start_stop_and_status(self):
        r=self.send(request(2));self.assertEqual(r[42+4:42+6],b'\x82\x00');self.assertEqual(r[42+8],2)  # starting
        self.assertEqual(self.c.wifi_ctl_poll(1,5000),ord('B'));self.assertEqual(self.c.wifi_ctl_poll(2,5000),-1)
        self.active.value=1
        self.assertEqual(self.send(request(4))[42+8],1)
        self.assertEqual(self.send(request(2))[42+8],1)       # idempotent while streaming
        self.assertEqual(self.c.wifi_ctl_poll(3,5000),-1)
        self.send(request(3));self.assertEqual(self.c.wifi_ctl_poll(4,5000),ord('E'))
    def test_stop_cancels_unstarted_request(self):
        self.send(request(2));self.send(request(3));self.assertEqual(self.c.wifi_ctl_poll(1,5000),-1)
    def test_watchdog_stops_only_control_started_streams(self):
        self.active.value=1;self.assertEqual(self.c.wifi_ctl_poll(100,5000),-1)
        self.assertEqual(self.c.wifi_ctl_poll(100000,5000),-1)   # UART-started stream is never stopped
        self.send(request(2));self.assertEqual(self.c.wifi_ctl_poll(100001,5000),-1)  # already active: no start
        self.assertEqual(self.c.wifi_ctl_poll(100002,5000),-1)
        self.assertEqual(self.c.wifi_ctl_poll(100002+5001,5000),ord('E'))
        self.assertEqual(self.c.wifi_ctl_poll(100002+20000,5000),-1)  # ownership released
    def test_keepalive_and_echo_traffic_feed_the_watchdog(self):
        self.send(request(2));self.c.wifi_ctl_poll(1000,5000);self.active.value=1
        self.c.wifi_ctl_poll(1001,5000)
        self.send(request(5));self.assertEqual(self.c.wifi_ctl_poll(5500,5000),-1)
        self.assertEqual(self.send(b'K',4201)[42:],b'K')                 # echo still works
        self.assertEqual(self.c.wifi_ctl_poll(10400,5000),-1)
        self.assertEqual(self.c.wifi_ctl_poll(15500,5000),ord('E'))
    def test_unknown_operation_and_malformed_requests(self):
        r=self.send(request(0x55));self.assertEqual(r[42+4:42+6],b'\xd5\x02')
        self.assertEqual(self.send(b'XXXX'+bytes(4)),b'');self.assertEqual(self.send(b'TCT1'),b'')
    def test_without_service_registered_port_4200_is_ignored(self):
        self.c.teardown();self.assertEqual(self.send(request(1)),b'')
if __name__=='__main__':unittest.main()
