"""Actual finite direct sender: guards, framing, credits and uncertain writes."""
import ctypes,pathlib,subprocess,tempfile,unittest,struct
from test_wifi_net import MAC,PEER,checksum
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Direct(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text(encoding='utf-8')
        a=source.index('/* Direct finite UDP diagnostic,');b=source.index('void sdio_wifi_more_data(void){',a)
        harness=r'''
#include <stdint.h>
#include <string.h>
#include "wifi_net.h"
static unsigned wifi_bench_active,wifi_bench_sent,wifi_bench_stalls,wifi_bench_failed;
static uint32_t wifi_bench_begin;
static uint8_t wifi_bench_body[1332];
static unsigned wifi_ap_active=1,wifi_peer_activated=1,wifi_tx_fault,wifi_sink_active,stream,raw_mode;
static unsigned wifi_tc1_free=14,wifi_data_tx,clock_now,window_slots=4,writes,reserved,write_error,poll_error;
static uint8_t wifi_mac[6]={0,3,0x69,7,0x1d,0x22},wifi_peer[6]={0x6c,0x4c,0xe2,0x0d,0x50,0xd4},saved[1536];
static unsigned xTaskGetTickCount(void){return clock_now;}
static int tuner_ts_stream_active(void){return stream;}
static unsigned sdio_wifi_raw_tx_selected(void){return raw_mode;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static void uart_puts(const char *s){(void)s;}
static int data_credit(unsigned n){(void)n;return poll_error;}
static unsigned ts_window_slots(void){return wifi_tc1_free?window_slots:0;}
static int extended_write(unsigned address,const uint8_t *p,unsigned n,int inc){
    (void)address;(void)inc;writes++;reserved=wifi_tc1_free;
    if(n!=sizeof saved)return -1;
    memcpy(saved,p,n);return write_error;
}
void state(unsigned mask){
    wifi_ap_active=!(mask&1);wifi_peer_activated=!(mask&2);wifi_tx_fault=mask&4;
    wifi_sink_active=mask&8;stream=mask&16;raw_mode=mask&32;clock_now=100;
    wifi_tc1_free=14;window_slots=4;writes=reserved=wifi_data_tx=0;
    write_error=poll_error=0;wifi_bench_active=wifi_bench_sent=wifi_bench_failed=0;
}
void credits(unsigned n){wifi_tc1_free=n;}
void window(unsigned n){window_slots=n;}
void tick(unsigned n){clock_now=n;}
void fail(unsigned n){write_error=n&1;poll_error=n&2;}
unsigned result(unsigned i){unsigned v[]={wifi_bench_active,wifi_bench_sent,wifi_bench_stalls,wifi_bench_failed,wifi_tc1_free,writes,reserved,wifi_tx_fault};return v[i];}
const uint8_t *packet(void){return saved;}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'direct.c').write_text(harness+source[a:b],encoding='utf-8')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(p/'direct.c'),str(ROOT/'src/wifi_net.c'),'-o',str(p/'direct.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'direct.so'));cls.c.packet.restype=ctypes.c_void_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def values(self):return [self.c.result(i) for i in range(8)]
    def test_guards_stall_and_timer_do_not_submit(self):
        for mask in (1,2,4,8,16,32):
            self.c.state(mask);self.c.sdio_wifi_tx_bench_start();self.c.sdio_wifi_tx_bench_poll()
            self.assertEqual(self.c.result(0),0);self.assertEqual(self.c.result(5),0)
        self.c.state(0);self.c.sdio_wifi_tx_bench_start();self.c.credits(0);self.c.sdio_wifi_tx_bench_poll()
        self.assertEqual(self.values(),[1,0,1,0,0,0,0,0])
        self.c.tick(10100);self.c.sdio_wifi_tx_bench_poll()
        self.assertEqual(self.c.result(0),0);self.assertEqual(self.c.result(5),0)
    def test_wire_payload_checksum_and_credit_reservation(self):
        self.c.state(0);self.c.sdio_wifi_tx_bench_start()
        for seq in (0,1):
            self.c.sdio_wifi_tx_bench_poll();p=ctypes.string_at(self.c.packet(),1536)
            self.assertEqual(p[:6],bytes.fromhex('6e050e040e10'))
            self.assertEqual(p[10:16],bytes([0,32,0,0,0,0]))
            f=p[16:1390];self.assertEqual(f[:12],PEER+MAC)
            self.assertEqual(checksum(f[14:34]),0)
            u=f[34:];self.assertEqual(u[:4],struct.pack('!HH',4204,4204))
            self.assertEqual(checksum(f[26:34]+struct.pack('!BBH',0,17,len(u))+u),0)
            body=u[8:];self.assertEqual(body[:12],b'TWT1'+struct.pack('!II',seq,1332))
            self.assertEqual(body[12:],bytes(i%251 for i in range(12,1332)))
            self.assertEqual(p[1390:],bytes(146))
            self.assertEqual(self.c.result(6),13-seq);self.assertEqual(self.c.result(1),seq+1)
    def test_uncertain_write_poison_never_refunds_or_retries(self):
        self.c.state(0);self.c.sdio_wifi_tx_bench_start();self.c.fail(1)
        self.c.sdio_wifi_tx_bench_poll();self.assertEqual(self.values(),[0,0,0,1,13,1,13,1])
        self.c.sdio_wifi_tx_bench_poll();self.assertEqual(self.c.result(5),1)
        self.c.state(0);self.c.sdio_wifi_tx_bench_start();self.c.fail(2)
        self.c.sdio_wifi_tx_bench_poll();self.assertEqual(self.c.result(5),0);self.assertEqual(self.c.result(4),14)
    def test_interrupt_and_wrap_deadline(self):
        self.c.state(0);self.c.tick(0xfffffff0);self.c.sdio_wifi_tx_bench_start()
        self.c.tick(0x00000005);self.c.sdio_wifi_tx_bench_poll();self.assertEqual(self.c.result(1),1)
        self.c.sdio_wifi_tx_bench_stop();self.c.sdio_wifi_tx_bench_poll();self.assertEqual(self.c.result(5),1)
if __name__=='__main__':unittest.main()
