"""Exercise actual handoff cleanup and ordering, replacing only hardware hooks."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Recovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sdio=(ROOT/'src/sdio.c').read_text();start=sdio.index('void sdio_wifi_quiesce(void){')
        cleanup=sdio[start:sdio.index('\nvoid sdio_wifi_ap(void)',start)]
        app=(ROOT/'src/app.c').read_text();start=app.index('void usb_idle(void){')
        handoff=app[start:app.index('\nvoid firmware_main',start)]
        handoff=handoff.replace('((void (*)(void))0xfff80000UL)();','enter_recovery();')
        harness=r'''
#include <stdint.h>
#include <string.h>
static unsigned wifi_hif_ready,wifi_ap_active,wifi_peer_state,wifi_ap_stop_ok,recover;
static unsigned order[16],events,disabled,stop_result,bad_deadline_order;
static uint16_t timer;
#define R16(a) timer
static void step(unsigned n){order[events++]=n;}
static void wifi_wpa_uart_close(void){step(12);}
static void tuner_ts_stream_interrupt(void){step(1);}
static void sdio_wifi_ap_stop(void){
    step(2);if(disabled)bad_deadline_order=1;wifi_ap_stop_ok=stop_result;
    wifi_ap_active=wifi_peer_state=0;
}
static void uart_puts(const char *s){
    step(strstr(s,"inactive")?3:strstr(s,"transferred")?4:5);
}
static void disable_interrupts(void){step(6);disabled=1;}
static int sdio_irq_set(unsigned n){(void)n;step(11);if(disabled)bad_deadline_order=1;return 0;}
#define portDISABLE_INTERRUPTS() disable_interrupts()
static unsigned instruction_cache_set(unsigned n){(void)n;step(7);return 0;}
static void usb_detach(void){step(8);}
static void enter_recovery(void){step(9);}
static void fault(void){step(10);}
void reset(unsigned requested,unsigned ready,unsigned active,unsigned peer,unsigned result){
    recover=requested;wifi_hif_ready=ready;wifi_ap_active=active;wifi_peer_state=peer;
    stop_result=result;events=disabled=bad_deadline_order=0;timer=1;
}
unsigned size(void){return events;}
unsigned event(unsigned n){return order[n];}
unsigned bad(void){return bad_deadline_order;}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'recover.c').write_text(harness+cleanup+handoff)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'recover.c'),'-o',str(p/'recover.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'recover.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def trace(self):return [self.c.event(i) for i in range(self.c.size())]
    def test_no_request_does_not_touch_radio_or_interrupts(self):
        self.c.reset(0,1,1,1,1);self.c.usb_idle();self.assertEqual(self.trace(),[])
    def test_live_radio_is_stopped_before_ticks_are_disabled(self):
        self.c.reset(1,1,1,1,1);self.c.usb_idle()
        self.assertEqual(self.trace(),[12,1,2,4,11,6,7,8,9,10]);self.assertEqual(self.c.bad(),0)
    def test_failed_cleanup_still_enters_recovery(self):
        self.c.reset(1,1,1,1,0);self.c.usb_idle()
        self.assertEqual(self.trace(),[12,1,2,5,11,6,7,8,9,10]);self.assertEqual(self.c.bad(),0)
    def test_inactive_or_uninitialized_radio_skips_bus_access(self):
        for ready,active,peer in ((0,1,1),(1,0,0)):
            self.c.reset(1,ready,active,peer,1);self.c.usb_idle()
            self.assertEqual(self.trace(),[12,1,3,11,6,7,8,9,10])
if __name__=='__main__':unittest.main()
