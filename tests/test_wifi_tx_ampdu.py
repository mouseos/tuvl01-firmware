import ctypes as C
import pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Ampdu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        text=(ROOT/'src/sdio.c').read_text()
        body=text[text.index('void sdio_wifi_tx_ampdu(void){'):text.index('static void status(void){')]
        harness=r'''
#include <stdint.h>
#include "wifi_ht.h"
static unsigned wifi_tx_ampdu_enabled,wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending;
static unsigned wifi_management_pending,wifi_data_count,wifi_bench_active,wifi_sink_active;
static unsigned wifi_ais_retained_active,wifi_connection_unresolved,wifi_ht_enabled;
static unsigned wifi_hif_ready,wifi_board_sent,wifi_tx_fault,wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc4_free,wifi_tc5_free;
static unsigned streaming,poll_fail,send_fail,calls,cid,length;static uint8_t wire[12];
static int tuner_ts_stream_active(void){return streaming;}
static int tx_poll(void){return poll_fail;}
static void uart_puts(const char *s){(void)s;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static int control_set(unsigned c,uint8_t *p,unsigned n){calls++;cid=c;length=n;for(unsigned i=0;i<n && i<12;i++)wire[i]=p[i];return send_fail;}
void reset(unsigned bad){
 wifi_tx_ampdu_enabled=calls=cid=length=0;
 wifi_ap_active=bad&1;wifi_peer_state=bad&2;wifi_peer_activate_pending=bad&4;
 wifi_management_pending=bad&8;wifi_data_count=bad&16;streaming=bad&32;
 wifi_bench_active=bad&64;wifi_sink_active=bad&128;wifi_ais_retained_active=bad&256;
 wifi_connection_unresolved=bad&512;wifi_ht_enabled=!(bad&1024);
 wifi_hif_ready=!(bad&2048);wifi_board_sent=!(bad&4096);wifi_tx_fault=bad&8192;
 poll_fail=bad&16384;wifi_tc1_free=bad&32768?13:14;wifi_tc2_free=bad&65536?0:1;
 wifi_tc3_free=bad&131072?0:1;wifi_tc4_free=bad&262144?3:4;wifi_tc5_free=bad&524288?0:1;
 send_fail=bad&1048576;
}
unsigned state(unsigned n){unsigned v[]={calls,cid,length,wifi_tx_ampdu_enabled,wifi_connection_unresolved};return v[n];}
unsigned byte(unsigned n){return wire[n];}
'''
        (p/'h.c').write_text(harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(p/'h.c'),str(ROOT/'src/wifi_ht.c'),'-o',str(p/'h.so')],check=True)
        cls.c=C.CDLL(str(p/'h.so'));cls.c.wifi_ht_ampdu_command.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_wire_and_invalid_requests_preserve_output(self):
        for enable in (0,1):
            out=(C.c_uint8*16)(*([165]*16))
            self.assertEqual(self.c.wifi_ht_ampdu_command(out,16,enable),1)
            self.assertEqual(bytes(out),bytes(8)+bytes([enable])+bytes(3)+bytes([165])*4)
        for cap,enable in ((11,1),(12,2),(12,255)):
            out=(C.c_uint8*12)(*([165]*12))
            self.assertEqual(self.c.wifi_ht_ampdu_command(out,cap,enable),0)
            self.assertEqual(bytes(out),bytes([165])*12)
        self.assertEqual(self.c.wifi_ht_ampdu_command(None,12,1),0)
    def test_every_active_state_and_credit_refuses_submission(self):
        for bit in range(20):
            self.c.reset(1<<bit);self.c.sdio_wifi_tx_ampdu()
            self.assertEqual(self.c.state(0),0);self.assertEqual(self.c.state(3),0)
    def test_transfer_toggle_and_uncertain_failure_latch(self):
        self.c.reset(0)
        for enable in (1,0):
            self.c.sdio_wifi_tx_ampdu()
            self.assertEqual([self.c.state(i) for i in (1,2,3,4)],[0x23,12,enable,0])
            self.assertEqual(bytes(self.c.byte(i) for i in range(12)),bytes(8)+bytes([enable])+bytes(3))
        self.c.reset(1048576);self.c.sdio_wifi_tx_ampdu()
        self.assertEqual([self.c.state(i) for i in (0,3,4)],[1,0,1])
        self.c.sdio_wifi_tx_ampdu();self.assertEqual(self.c.state(0),1)
