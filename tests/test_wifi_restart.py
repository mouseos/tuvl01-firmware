"""Run the actual restart procedure with bounded, fallible hardware hooks."""
import ctypes
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Restart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'src/sdio.c').read_text()
        start = source.index('void sdio_wifi_restart(void){')
        body = source[start:source.index('\nvoid sdio_wifi_mac(void)', start)]
        harness = r'''
#include <stdint.h>
#include <string.h>
#include "wifi_scan_cache.h"
static struct wifi_scan_cache wifi_bss_cache;
static unsigned wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending;
static unsigned wifi_management_pending,wifi_data_count,wifi_scan_active,wifi_scan_unresolved;
static unsigned wifi_connection_unresolved;
static unsigned wifi_bench_active,wifi_sink_active,stream;
static struct { unsigned pending; } wifi_feedback;
static unsigned card_verified,wifi_hif_ready,wifi_tx_fault;
static unsigned wifi_mac_valid,wifi_board_sent;
static unsigned wifi_dpd_attempted,wifi_dpd_transferred;
static unsigned wifi_osc_attempted;
static unsigned wifi_per_attempted,wifi_per_transferred,wifi_per_steps;
static unsigned wifi_sequence,wifi_channel_token;
static unsigned wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc4_free,wifi_tc5_free;
static unsigned wifi_credit_fresh,wifi_credit_probe,wifi_status_polling,wifi_poll_reuse;
static unsigned wifi_status_rx,wifi_management_length,wifi_peer_active,wifi_peer_activated;
static unsigned wifi_ap_stop_ok;
static struct wifi_ht_peer { unsigned enabled; } wifi_peer_ht;
static unsigned wifi_power;
static uint16_t clock_reg;
#define S(a) clock_reg
static unsigned mode,phase,delay,events,trace[20],ready,failed,refused,bad;
static void event(unsigned n){trace[events++]=n;}
static unsigned tuner_ts_stream_active(void){return stream;}
static int radio_image_valid(void){return mode!=14;}
static void uart_puts(const char *s){
 if(!strcmp(s,"WIFI restart end status=ready\n"))ready++;
 if(!strcmp(s,"WIFI restart end status=failed\n"))failed++;
 if(strstr(s,"refused-"))refused++;
}
static void field(const char *s,uint32_t n){(void)s;(void)n;}
static int radio_read(unsigned a,uint32_t *v){
 if(a==4){event(10);*v=mode==13?0:0x100;return 0;}
 if(a!=0)return -1;
 if(phase==0){event(1);*v=mode==2?0x205930:0x205931;return mode==1?-1:0;}
 if(phase==1){event(7);*v=mode==9?0x205931:mode==10?0x5930:0x5931;return 0;}
 event(9);*v=mode==12?0x5931:0x205931;return 0;
}
static int radio_write(unsigned a,uint32_t v){
 if(a==4 && v==0x200){event(2);return mode==3?-1:0;}
 if(a!=0x8c)return -1;
 if(v==0x8000){event(4);return mode==6?-1:0;}
 if(v==0){event(5);phase=1;return mode==7?-1:0;}
 return -1;
}
static int radio_wait(unsigned a,uint32_t mask,uint32_t reject){
 if(reject)bad++;
 if(a==4 && mask==0x100){event(3);return mode==4?-1:0;}
 if(a==0x8c && mask==0x800){event(6);if(delay<120)bad++;return mode==8?-1:0;}
 return -1;
}
static int sdio_irq_set(unsigned n){if(n)bad++;return mode==5?-1:0;}
static void vTaskDelay(unsigned n){delay+=n;}
static void wifi_power_events_reset(unsigned *p){*p=0;}
static int radio_boot(unsigned force){
 event(8);if(phase!=1 || delay<120 || wifi_tc4_free || wifi_hif_ready)bad++;
 if(force!=1)bad++;
 phase=2;if(mode==11){card_verified=0;return -1;}
 return 0;
}
void reset(unsigned selected,unsigned active){
 wifi_bss_cache.complete=1;wifi_bss_cache.active=0;wifi_bss_cache.count=1;
 mode=selected;phase=delay=events=ready=failed=refused=bad=0;wifi_scan_unresolved=1;
 wifi_connection_unresolved=1;
 wifi_ap_active=active&1;wifi_peer_state=active&2;wifi_peer_activate_pending=active&4;
 wifi_management_pending=active&8;wifi_data_count=active&16;wifi_scan_active=active&32;
 wifi_bench_active=active&64;wifi_sink_active=active&128;wifi_feedback.pending=active&256;
 stream=active&512;card_verified=mode!=15;clock_reg=mode==16?0:0x100;
 wifi_hif_ready=1;wifi_tx_fault=1;wifi_tc4_free=2;
 wifi_mac_valid=wifi_board_sent=wifi_dpd_attempted=wifi_dpd_transferred=1;
 wifi_osc_attempted=1;
 wifi_per_attempted=wifi_per_transferred=wifi_per_steps=1;
 wifi_sequence=255;wifi_channel_token=31;
 wifi_tc1_free=14;wifi_tc2_free=wifi_tc3_free=wifi_tc5_free=1;
 wifi_credit_probe=wifi_status_polling=wifi_poll_reuse=1;
}
unsigned cache_complete(void){return wifi_bss_cache.complete;}
unsigned connection_unresolved(void){return wifi_connection_unresolved;}
unsigned oscillator_attempted(void){return wifi_osc_attempted;}
unsigned state(unsigned i){unsigned v[]={ready,failed,refused,wifi_hif_ready,
 wifi_tx_fault,wifi_tc4_free,delay,bad,events,wifi_mac_valid,wifi_board_sent,
 wifi_dpd_attempted,wifi_per_attempted,wifi_credit_probe,wifi_status_polling,
 wifi_poll_reuse,wifi_scan_unresolved};return v[i];}
unsigned step(unsigned i){return trace[i];}
'''
        cls.tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(cls.tmp.name)
        (path / 'restart.c').write_text(harness + body)
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-iquote'+str(ROOT/'include'),str(path / 'restart.c'),
                        str(ROOT/'src/wifi_scan_cache.c'), '-o', str(path / 'restart.so')], check=True)
        cls.c = ctypes.CDLL(str(path / 'restart.so'))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def state(self):
        return [self.c.state(i) for i in range(16)]

    def test_reset_order_confirmed_before_reload_and_no_credit_is_invented(self):
        self.c.reset(0, 0)
        self.c.sdio_wifi_restart()
        self.assertEqual([self.c.step(i) for i in range(self.c.state(8))], list(range(1, 11)))
        self.assertEqual(self.state()[:8], [1, 0, 0, 0, 0, 0, 120, 0])
        self.assertEqual(self.state()[9:], [0] * 7)
        self.assertEqual(self.c.state(16), 0)
        self.assertEqual(self.c.connection_unresolved(),0)
        self.assertEqual(self.c.oscillator_attempted(),0)

    def test_real_restart_invalidates_scan_cache_but_refused_restart_does_not(self):
        self.c.reset(0,0);self.c.sdio_wifi_restart()
        self.assertEqual(self.c.cache_complete(),0)
        self.c.reset(0,1);self.c.sdio_wifi_restart()
        self.assertEqual(self.c.cache_complete(),1)

    def test_active_traffic_is_untouched(self):
        for active in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512):
            self.c.reset(0, active)
            self.c.sdio_wifi_restart()
            self.assertEqual(self.state()[:6], [0, 0, 1, 1, 1, 2], active)
            self.assertEqual(self.c.state(8), 0)
            self.assertEqual(self.c.oscillator_attempted(),1)

    def test_invalid_image_card_or_clock_prevents_any_hardware_write(self):
        for mode in (14, 15, 16):
            self.c.reset(mode, 0)
            self.c.sdio_wifi_restart()
            self.assertEqual(self.state()[:3], [0, 0, 1])
            self.assertEqual(self.c.state(8), 0)

    def test_retained_hif_ready_still_requires_full_firmware_reload(self):
        self.c.reset(9, 0)
        self.c.sdio_wifi_restart()
        self.assertEqual(self.state()[:8], [1, 0, 0, 0, 0, 0, 120, 0])
        self.assertIn(8, [self.c.step(i) for i in range(self.c.state(8))])

    def test_hardware_and_reload_failures_cannot_report_new_session(self):
        for mode in range(1, 14):
            if mode == 9:
                continue
            self.c.reset(mode, 0)
            self.c.sdio_wifi_restart()
            self.assertEqual(self.state()[:5], [0, 1, 0, 0, 1], mode)
            self.assertEqual(self.c.state(7), 0, mode)
            self.assertEqual(self.c.state(16), 1, mode)
            self.assertEqual(self.c.connection_unresolved(),1,mode)
            if mode < 11:
                self.assertNotIn(8, [self.c.step(i) for i in range(self.c.state(8))], mode)


if __name__ == '__main__':
    unittest.main()
