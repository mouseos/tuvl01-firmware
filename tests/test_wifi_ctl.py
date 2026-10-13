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
        cls.so=p/'ctl.so';cls.n=0
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        # A private copy of the library per test: the service keeps its state in globals.
        Control.n+=1;path=pathlib.Path(self.tmp.name)/f'ctl{Control.n}.so';path.write_bytes(self.so.read_bytes())
        c=self.c=ctypes.CDLL(str(path))
        c.wifi_net_reply.restype=ctypes.c_uint
        c.wifi_net_reply.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint]
        c.wifi_ctl_poll.restype=ctypes.c_int;c.wifi_ctl_poll.argtypes=[ctypes.c_uint,ctypes.c_uint]
        c.wifi_ctl_take_tune.argtypes=[ctypes.c_void_p,ctypes.c_void_p];c.wifi_ctl_tune_done.argtypes=[ctypes.c_int]
        c.wifi_ctl_set_lock.argtypes=[ctypes.c_uint]
        self.active=ctypes.c_int.in_dll(c,'stub_active');self.active.value=0
        c.setup();c.wifi_ctl_poll(0,10**9)
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
        version,rev,caps,port,state,first,last=struct.unpack('!BHIHBBB',body[8:20])
        self.assertEqual((version,rev,caps,port,state,first,last),(1,168,3,4202,0,13,52))
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
    def tune(self,channel,mode=0):return self.send(request(6,0x77,bytes([channel,mode])))
    def status(self):
        r=self.send(request(4));self.assertEqual(r[42+4:42+6],b'\x84\x00');return struct.unpack('!BHBBB',r[42+8:42+14])
    def test_tune_is_queued_reported_busy_and_completed(self):
        r=self.tune(25,1);self.assertEqual(r[42+4:42+6],b'\x86\x00');self.assertEqual(r[42+8],1)
        self.assertEqual(self.status(),(0,0,0,1,255))                    # busy, nothing tuned yet
        ch=ctypes.c_uint();mode=ctypes.c_uint()
        self.assertEqual(self.c.wifi_ctl_take_tune(ctypes.byref(ch),ctypes.byref(mode)),1);self.assertEqual((ch.value,mode.value),(25,1))
        self.assertEqual(self.c.wifi_ctl_take_tune(ctypes.byref(ch),ctypes.byref(mode)),0)  # delivered once
        self.c.wifi_ctl_tune_done(1);self.assertEqual(self.status(),(0,25,1,2,255))
        self.c.wifi_ctl_set_lock(1);self.assertEqual(self.status(),(0,25,1,2,1))
    def test_failed_tune_keeps_previous_channel(self):
        ch=ctypes.c_uint();mode=ctypes.c_uint()
        self.tune(30);self.c.wifi_ctl_take_tune(ctypes.byref(ch),ctypes.byref(mode));self.c.wifi_ctl_tune_done(1)
        self.tune(40);self.c.wifi_ctl_take_tune(ctypes.byref(ch),ctypes.byref(mode));self.c.wifi_ctl_tune_done(0)
        self.assertEqual(self.status()[:4],(0,30,0,3))
    def test_tune_arriving_during_a_tune_stays_busy(self):
        ch=ctypes.c_uint();mode=ctypes.c_uint()
        self.tune(30);self.c.wifi_ctl_take_tune(ctypes.byref(ch),ctypes.byref(mode))
        self.tune(31);self.c.wifi_ctl_tune_done(1)
        self.assertEqual(self.status()[3],1);self.assertEqual(self.c.wifi_ctl_take_tune(ctypes.byref(ch),ctypes.byref(mode)),1)
        self.assertEqual(ch.value,31)
    def test_tune_rejects_bad_channel_mode_and_short_request(self):
        for body in (request(6,1,bytes([12,0])),request(6,1,bytes([53,0])),request(6,1,bytes([25,2])),request(6,1,b'')):
            r=self.send(body);self.assertEqual(r[42+5],1,body)
        self.assertEqual(self.status()[3],0)
    def test_tune_cancels_a_queued_start(self):
        self.send(request(2));self.tune(20);self.assertEqual(self.c.wifi_ctl_poll(1,5000),-1)
    def test_without_service_registered_port_4200_is_ignored(self):
        self.c.teardown();self.assertEqual(self.send(request(1)),b'')
if __name__=='__main__':unittest.main()



