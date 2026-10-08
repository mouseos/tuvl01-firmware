"""Actual-C one-shot DPD request: idle guards and complete wire envelope."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class DPD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=(ROOT/'src/sdio.c').read_text(encoding='utf-8')
        a=s.index('void sdio_wifi_dpd(void){');b=s.index('void sdio_wifi_ap_stop(void){',a)
        harness=r'''
#include <stdint.h>
#include <string.h>
static unsigned wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending,wifi_management_pending,wifi_data_count;
static unsigned wifi_dpd_attempted,wifi_dpd_transferred,wifi_hif_ready,wifi_board_sent,wifi_tx_fault;
static unsigned wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc4_free,wifi_tc5_free;
static unsigned poll_error,send_error,calls,cid,size;
static uint8_t saved[32];
static int tx_poll(void){return poll_error?-1:0;}
static void uart_puts(const char *s){(void)s;}
static int control_set(unsigned c,uint8_t *p,unsigned n){
    calls++;cid=c;size=n;if(n==sizeof saved)memcpy(saved,p,n);return send_error?-1:0;
}
void reset(unsigned mask){
    wifi_ap_active=mask&1;wifi_peer_state=mask&2;wifi_peer_activate_pending=mask&4;
    wifi_management_pending=mask&8;wifi_data_count=mask&16;
    wifi_hif_ready=!(mask&32);wifi_board_sent=!(mask&64);wifi_tx_fault=mask&128;
    poll_error=mask&256;send_error=mask&512;
    wifi_tc1_free=14;wifi_tc2_free=wifi_tc3_free=wifi_tc5_free=1;wifi_tc4_free=4;
    wifi_dpd_attempted=wifi_dpd_transferred=calls=cid=size=0;memset(saved,0xff,sizeof saved);
}
void pending(unsigned tc){switch(tc){case 1:wifi_tc1_free--;break;case 2:wifi_tc2_free--;break;case 3:wifi_tc3_free--;break;case 4:wifi_tc4_free--;break;case 5:wifi_tc5_free--;break;}}
unsigned result(unsigned n){unsigned v[]={calls,cid,size,wifi_dpd_attempted,wifi_dpd_transferred};return v[n];}
const uint8_t *packet(void){return saved;}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'dpd.c').write_text(harness+s[a:b],encoding='utf-8')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'dpd.c'),'-o',str(p/'dpd.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'dpd.so'));cls.c.packet.restype=ctypes.c_void_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def values(self):return [self.c.result(i) for i in range(5)]
    def test_guards_do_not_consume_attempt(self):
        for mask in (1,2,4,8,16,32,64,128,256):
            self.c.reset(mask);self.c.sdio_wifi_dpd();self.assertEqual(self.values(),[0,0,0,0,0])
        for tc in range(1,6):
            self.c.reset(0);self.c.pending(tc);self.c.sdio_wifi_dpd();self.assertEqual(self.values(),[0,0,0,0,0])
    def test_complete_envelope_and_no_repeated_request(self):
        self.c.reset(0);self.c.sdio_wifi_dpd()
        self.assertEqual(self.values(),[1,0xf1,32,1,1])
        expected=bytearray(32);expected[13]=1;expected[15]=128
        self.assertEqual(ctypes.string_at(self.c.packet(),32),bytes(expected))
        self.c.sdio_wifi_dpd();self.assertEqual(self.values(),[1,0xf1,32,1,1])
    def test_failed_transfer_still_consumes_attempt_without_success(self):
        self.c.reset(512);self.c.sdio_wifi_dpd();self.assertEqual(self.values(),[1,0xf1,32,1,0])
        self.c.sdio_wifi_dpd();self.assertEqual(self.values(),[1,0xf1,32,1,0])
if __name__=='__main__':unittest.main()
