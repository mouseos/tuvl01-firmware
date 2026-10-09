"""Exercise the real bounded NIC shutdown/sample/reload diagnostic."""
import ctypes
import pathlib
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class QuietSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=(ROOT/'src/sdio.c').read_text()
        body=s[s.index('void sdio_wifi_quiet_sample('):s.index('void sdio_wifi_width(')]
        harness=r'''
#include <stdint.h>
#include <string.h>
typedef unsigned TickType_t;
#define pdMS_TO_TICKS(n) (n)
static unsigned card_verified,wifi_hif_ready,wifi_tx_fault,wifi_mac_valid,wifi_board_sent;
static unsigned wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc4_free,wifi_tc5_free;
static unsigned mode,active,reads,writes,sent,sampled,restarted,bad,tick,phase;
static uint16_t clock_reg;
static char status[100];
#define S(a) clock_reg
static int sdio_wifi_traffic_active(void){return active;}
static int radio_image_valid(void){return mode!=2;}
static int radio_read(unsigned a,uint32_t *v){
 reads++;
 if(a==0){*v=phase?0x5931:0x205931;if(mode==6 && phase)*v=0x205931;return mode==3?-1:0;}
 *v=phase>=2?0:0x100;if(mode==8 && phase>=2)*v=0x100;return 0;
}
static int radio_write(unsigned a,uint32_t v){
 writes++;if(a!=4)bad++;
 if(v==0x100){phase=2;return mode==7?-1:0;}
 if(v!=0x200)bad++;
 return mode==9?-1:0;
}
static int sdio_irq_set(unsigned n){if(n)bad++;return mode==4?-1:0;}
static int control_send(unsigned cid,unsigned set,uint8_t *p,unsigned len){
 if(cid!=5 || set!=1 || len!=12 || p[8]!=1 || p[9] || p[10] || p[11] || !wifi_hif_ready || wifi_tx_fault)bad++;
 sent++;phase=1;return mode==5?-1:0;
}
static void sdio_wifi_restart(void){
 restarted++;if(wifi_hif_ready || !wifi_tx_fault || wifi_mac_valid || wifi_board_sent || wifi_tc4_free)bad++;
 if(mode!=9 && mode!=10 && mode!=11)wifi_tx_fault=0;
}
static void sample(void){if(phase!=2 || tick<1501 || wifi_hif_ready || !wifi_tx_fault)bad++;sampled++;}
static TickType_t xTaskGetTickCount(void){return tick;}
static void vTaskDelay(unsigned n){tick+=n;}
static void field(const char *s,uint32_t v){(void)s;(void)v;}
static void uart_puts(const char *s){
 if(strstr(s,"end status="))status[0]=0;
 if(strlen(status)+strlen(s)<sizeof status)strcat(status,s);
}
void reset(unsigned m,unsigned a){
 mode=m;active=a;reads=writes=sent=sampled=restarted=bad=tick=phase=0;
 card_verified=1;wifi_hif_ready=wifi_mac_valid=wifi_board_sent=1;wifi_tx_fault=0;
 wifi_tc1_free=14;wifi_tc2_free=wifi_tc3_free=wifi_tc5_free=1;wifi_tc4_free=4;
 clock_reg=m==1?0:0x100;status[0]=0;
}
unsigned state(unsigned i){unsigned v[]={reads,writes,sent,sampled,restarted,bad,tick,wifi_hif_ready,wifi_tx_fault,wifi_mac_valid,wifi_board_sent,wifi_tc4_free};return v[i];}
const char *result(void){return status;}
'''
        cls.tmp=tempfile.TemporaryDirectory()
        p=pathlib.Path(cls.tmp.name)
        (p/'quiet.c').write_text(harness+body+'\nvoid run(unsigned null){sdio_wifi_quiet_sample(null?0:sample);}')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'quiet.c'),'-o',str(p/'quiet.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'quiet.so'));cls.c.result.restype=ctypes.c_char_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_mode(self,m=0,a=0,null=0):
        self.c.reset(m,a);self.c.run(null)
        self.assertEqual(self.c.state(5),0)
        return self.c.result().decode()
    def test_success_samples_only_after_shutdown_and_invalidates_session(self):
        self.assertIn('sampled-restarted',self.run_mode())
        self.assertEqual([self.c.state(i) for i in (2,3,4,7,8,9,10,11)],[1,1,1,0,0,0,0,0])
    def test_preflight_refusals_do_not_submit_or_reload(self):
        for m,a,null in [(1,0,0),(2,0,0),(3,0,0),(4,0,0),(0,1,0),(0,0,1)]:
            self.assertIn('refused-',self.run_mode(m,a,null))
            self.assertEqual([self.c.state(i) for i in (1,2,3,4)],[0,0,0,0])
            self.assertEqual(self.c.state(7),1)
    def test_uncertain_submission_stop_timeout_or_handoff_failure_still_reload(self):
        for m in (5,6,7,8):
            self.assertIn('failed-restarted',self.run_mode(m))
            self.assertEqual([self.c.state(i) for i in (2,3,4,7,8)],[1,0,1,0,0])
        self.run_mode(6);self.assertLessEqual(self.c.state(6),5000)
    def test_reset_or_reload_failure_blocks_old_hif(self):
        for m in (9,10,11):
            self.assertIn('restart-failed',self.run_mode(m))
            self.assertEqual([self.c.state(i) for i in (7,8,9,10,11)],[0,1,0,0,0])
if __name__=='__main__':unittest.main()
