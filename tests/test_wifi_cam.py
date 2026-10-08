"""Actual-C guarded CAM request with explicit unavailable readback."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class CAM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text();start=source.index('void sdio_wifi_cam(void){')
        actual=source[start:source.index('void sdio_wifi_rate_profile(void){',start)]
        harness=r'''
#include <stdint.h>
#include <string.h>
static unsigned wifi_peer_state,wifi_peer_activate_pending,wifi_management_pending;
static unsigned wifi_ap_active,wifi_hif_ready,wifi_tx_fault,wifi_tc1_free,wifi_tc4_free,wifi_tc5_free;
static unsigned fail,poll_fail,calls,cid,size;static uint8_t saved[12];static char status[64];
static int tx_poll(void){return poll_fail?-1:0;}
static int control_set(unsigned c,uint8_t *p,unsigned n){calls++;cid=c;size=n;memcpy(saved,p,n);return fail?-1:0;}
static void uart_puts(const char *s){if(strstr(s,"end status=")){strncpy(status,s,63);status[63]=0;}}
void run(unsigned mode){
    wifi_peer_state=wifi_peer_activate_pending=wifi_management_pending=wifi_tx_fault=fail=poll_fail=0;
    wifi_ap_active=wifi_hif_ready=1;wifi_tc1_free=14;wifi_tc4_free=4;wifi_tc5_free=1;calls=cid=size=0;
    memset(saved,0xa5,12);status[0]=0;
    switch(mode){case 1:wifi_peer_state=1;break;case 2:wifi_peer_activate_pending=1;break;
    case 3:wifi_management_pending=1;break;case 4:wifi_ap_active=0;break;case 5:wifi_hif_ready=0;break;
    case 6:wifi_tx_fault=1;break;case 7:poll_fail=1;break;case 8:wifi_tc1_free=13;break;
    case 9:wifi_tc4_free=3;break;case 10:wifi_tc5_free=0;break;case 11:fail=1;break;}
    sdio_wifi_cam();
}
const char *end(void){return status;} const uint8_t *packet(void){return saved;}
unsigned value(unsigned n){unsigned v[]={calls,cid,size,wifi_tc1_free,wifi_tc4_free,wifi_tc5_free};return v[n];}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'cam.c').write_text('void sdio_wifi_cam(void);\n'+harness+actual)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'cam.c'),'-o',str(p/'cam.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'cam.so'));cls.c.end.restype=ctypes.c_char_p;cls.c.packet.restype=ctypes.c_void_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_wire_profile_and_transfer_scope(self):
        self.c.run(0);self.assertIn(b'=transferred',self.c.end())
        self.assertEqual([self.c.value(i) for i in range(6)],[1,6,12,14,4,1])
        self.assertEqual(ctypes.string_at(self.c.packet(),12),bytes(8)+b'\1\0\0\0')
    def test_peer_or_uncertain_resource_state_never_sends(self):
        for mode in range(1,11):
            self.c.run(mode);self.assertIn(b'=refused-',self.c.end());self.assertEqual(self.c.value(0),0)
            self.assertEqual(ctypes.string_at(self.c.packet(),12),bytes([0xa5])*12)
    def test_control_failure_never_reports_verified_or_transferred(self):
        self.c.run(11);self.assertIn(b'=failed',self.c.end());self.assertNotIn(b'=transferred',self.c.end())
if __name__=='__main__':unittest.main()
