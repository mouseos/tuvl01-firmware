"""Run the actual idle-only OSC command and inspect its wire body."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class OSC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=(ROOT/'src/sdio.c').read_text(encoding='utf-8')
        a=s.index('void sdio_wifi_osc(void){');b=s.index('void sdio_wifi_board(void){',a)
        harness=r'''
#include <stdint.h>
#include <string.h>
static unsigned wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending,wifi_management_pending,wifi_data_count;
static unsigned wifi_osc_attempted,wifi_hif_ready,wifi_tx_fault,wifi_ais_retained_active,wifi_connection_unresolved;
static unsigned wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc4_free,wifi_tc5_free;
static unsigned stream,poll_error,send_error,calls,cid,size;
static uint8_t saved[16];
static int tuner_ts_stream_active(void){return stream;}
static int tx_poll(void){return poll_error?-1:0;}
static void uart_puts(const char *s){(void)s;}
static int control_set(unsigned c,uint8_t *p,unsigned n){
 calls++;cid=c;size=n;if(n==sizeof saved)memcpy(saved,p,n);return send_error?-1:0;
}
void reset(unsigned mask){
 wifi_ap_active=mask&1;wifi_peer_state=mask&2;wifi_peer_activate_pending=mask&4;
 wifi_management_pending=mask&8;wifi_data_count=mask&16;stream=mask&32;
 wifi_ais_retained_active=mask&64;wifi_connection_unresolved=mask&128;
 wifi_hif_ready=!(mask&256);wifi_tx_fault=mask&512;poll_error=mask&1024;send_error=mask&2048;
 wifi_tc1_free=14;wifi_tc2_free=wifi_tc3_free=wifi_tc5_free=1;wifi_tc4_free=4;
 wifi_osc_attempted=calls=cid=size=0;memset(saved,0xff,sizeof saved);
}
void pending(unsigned tc){switch(tc){case 1:wifi_tc1_free--;break;case 2:wifi_tc2_free--;break;case 3:wifi_tc3_free--;break;case 4:wifi_tc4_free--;break;case 5:wifi_tc5_free--;break;}}
unsigned result(unsigned n){unsigned v[]={calls,cid,size,wifi_osc_attempted};return v[n];}
const uint8_t *packet(void){return saved;}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'osc.c').write_text(harness+s[a:b],encoding='utf-8')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'osc.c'),'-o',str(p/'osc.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'osc.so'));cls.c.packet.restype=ctypes.c_void_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def state(self):return [self.c.result(i) for i in range(4)]
    def test_active_unready_fault_and_credit_guards(self):
        for bit in range(11):
            self.c.reset(1<<bit);self.c.sdio_wifi_osc();self.assertEqual(self.state(),[0,0,0,0])
        for tc in range(1,6):
            self.c.reset(0);self.c.pending(tc);self.c.sdio_wifi_osc();self.assertEqual(self.state(),[0,0,0,0])
    def test_little_endian_zero_and_reserved_body_once(self):
        self.c.reset(0);self.c.sdio_wifi_osc();self.assertEqual(self.state(),[1,0xf2,16,1])
        self.assertEqual(ctypes.string_at(self.c.packet(),16),bytes(16))
        self.c.sdio_wifi_osc();self.assertEqual(self.state(),[1,0xf2,16,1])
    def test_uncertain_transfer_is_not_retried(self):
        self.c.reset(2048);self.c.sdio_wifi_osc();self.assertEqual(self.state(),[1,0xf2,16,1])
        self.c.sdio_wifi_osc();self.assertEqual(self.state(),[1,0xf2,16,1])
if __name__=='__main__':unittest.main()
