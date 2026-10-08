"""Passive scan bytes plus actual board scan lifecycle under controlled RX."""
import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Scan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); p = pathlib.Path(cls.tmp.name)
        source = (ROOT/'src/sdio.c').read_text()
        start = source.index('void sdio_wifi_scan(void){')
        body = source[start:source.index('\nstatic unsigned ais_lease_left(', start)]
        ap_start = source.index('void sdio_wifi_ap(void){')
        ap_guard = source[ap_start:source.index('    const struct wifi_rates *rates=', ap_start)]
        ap_guard += 'submissions++;}\n'
        harness = r'''
#include <stdint.h>
#include <string.h>
#include "wifi_scan.h"
#include "wifi_scan_cache.h"
static struct wifi_scan_cache wifi_bss_cache;
typedef uint32_t TickType_t;
static unsigned wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending;
static unsigned wifi_management_pending,wifi_bench_active,wifi_sink_active;
static unsigned wifi_scan_active,wifi_beacons,wifi_scan_unresolved;
static uint8_t wifi_sequence,saved[120],saved_cancel[12];
static unsigned mode,activation,deactivation,submissions,rx,ready,failed,bounded,refused;
static unsigned cancellations,trace[8],trace_count;
static uint32_t ticks;
static int same_text(const char *a,const char *b){
 unsigned i=0;while(a[i] && a[i]==b[i])i++;
 return a[i]==b[i];
}
static void uart_puts(const char *s){
 if(same_text(s,"WIFI passive scan end status=ready\n"))ready++;
 if(same_text(s,"WIFI passive scan end status=failed\n"))failed++;
 if(same_text(s,"WIFI passive scan end status=refused-active\n"))refused++;
 if(same_text(s,"WIFI passive scan end status=refused-unresolved\n"))refused++;
 if(same_text(s,"WIFI scan tail status=bounded\n"))bounded++;
}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static TickType_t xTaskGetTickCount(void){return ticks;}
static void vTaskDelay(unsigned n){ticks+=n;}
static int radio_read(unsigned a,uint32_t *v){if(a!=0x50)return -1;*v=rx<2?64:0;return 0;}
static int control_set(unsigned cid,uint8_t *p,unsigned n){
 if(cid==0x1f){
  cancellations++;trace[trace_count++]=2;
  if(n!=12 || p[8]!=saved[8])return -1;
  for(unsigned i=0;i<12;i++)if(i!=8 && p[i])return -1;
  memcpy(saved_cancel,p,n);if(mode==8)return -1;
  if(!++wifi_sequence)++wifi_sequence;
  return 0;
 }
 if(cid!=0x15 || n!=12 || p[8])return -1;
 if(p[9]){activation++;trace[trace_count++]=1;if(mode==7)return -1;}
 else{deactivation++;trace[trace_count++]=3;if(mode==6)return -1;}
 if(!++wifi_sequence)++wifi_sequence;
 return 0;
}
static int control_send(unsigned cid,unsigned set,uint8_t *p,unsigned n){
 if(cid!=0x1e || set!=1 || n!=120)return -1;
 submissions++;memcpy(saved,p,n);if(mode==2)return -1;
 if(!++wifi_sequence)++wifi_sequence;
 return 0;
}
static int event_read(uint8_t *p,unsigned cap,unsigned *n){
 (void)cap;if(mode==4)return -1;
 if(mode==3 || mode==8){*n=0;return 0;}
 if(!rx++){
  memset(p,0,12);p[0]=12;p[2]=1;p[4]=0x15;p[8]=saved[8]+(mode==1);
  *n=12;return 1;
 }
 if(rx==2 || mode==5){
  struct wifi_ais_beacon b={0};b.ap[0]=2;b.ap[5]=1;b.channel=b.rx_channel=11;
  wifi_scan_cache_observe(&wifi_bss_cache,&b,ticks,0,100);
  *n=64;wifi_beacons++;return 0;
 }
 *n=0;return 0;
}
void reset(unsigned selected_mode,unsigned active,uint32_t tick){
 mode=selected_mode;wifi_ap_active=active&1;wifi_peer_state=active&2;
 wifi_peer_activate_pending=active&4;wifi_management_pending=active&8;
 wifi_bench_active=active&16;wifi_sink_active=active&32;
 wifi_sequence=0;wifi_beacons=99;wifi_scan_active=0;
 wifi_scan_unresolved=cancellations=trace_count=0;
 activation=deactivation=submissions=rx=ready=failed=bounded=refused=0;ticks=tick;
}
unsigned state(unsigned i){unsigned s[]={activation,deactivation,submissions,rx,
 ready,failed,bounded,refused,wifi_scan_active,wifi_beacons,wifi_scan_unresolved,cancellations};return s[i];}
const uint8_t *request(void){return saved;}
const uint8_t *cancel_request(void){return saved_cancel;}
void sequence(unsigned n){wifi_sequence=(uint8_t)n;}
void unresolved(unsigned n){wifi_scan_unresolved=n;}
unsigned step(unsigned n){return trace[n];}
unsigned cache_state(unsigned i){unsigned s[]={wifi_bss_cache.active,wifi_bss_cache.complete,wifi_bss_cache.count};return s[i];}
'''
        (p/'scan.c').write_text(harness+body+ap_guard)
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT/'include'), str(p/'scan.c'),
                        str(ROOT/'src/wifi_scan.c'),str(ROOT/'src/wifi_scan_cache.c'), '-o', str(p/'scan.so')], check=True)
        cls.c = C.CDLL(str(p/'scan.so')); cls.c.request.restype = C.c_void_p
        cls.c.cancel_request.restype = C.c_void_p
        cls.c.reset.argtypes = [C.c_uint, C.c_uint, C.c_uint32]
        cls.c.wifi_scan_passive.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_uint, C.c_uint]
        cls.c.wifi_scan_done.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
        cls.c.wifi_scan_cancel.argtypes = [C.c_void_p, C.c_uint, C.c_uint]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def states(self):
        return [self.c.state(i) for i in range(10)]

    def test_all_channels_entire_packet_and_legacy_channel_one(self):
        out = C.create_string_buffer(120)
        for first, last in [(1, 13), (1, 1), (6, 11)]:
            self.assertEqual(self.c.wifi_scan_passive(out, 120, 255, first, last), 120)
            expected = bytearray(120); expected[8] = 255; expected[11] = 1
            expected[14] = expected[48] = 100; expected[50] = 4; expected[51] = last-first+1
            for i, channel in enumerate(range(first, last+1)):
                expected[52+i*2:54+i*2] = bytes([1, channel])
            self.assertEqual(out.raw, bytes(expected))

    def test_invalid_request_keeps_output(self):
        out = C.create_string_buffer(b'X'*120, 120)
        for cap, seq, first, last in [(119, 1, 1, 13), (120, 0, 1, 13),
                       (120, 256, 1, 13), (120, 1, 0, 13), (120, 1, 1, 14), (120, 1, 6, 1)]:
            self.assertEqual(self.c.wifi_scan_passive(out, cap, seq, first, last), 0)
            self.assertEqual(out.raw, b'X'*120)
        self.assertEqual(self.c.wifi_scan_passive(None, 120, 1, 1, 13), 0)

    def test_actual_scan_only_publishes_cache_after_successful_cleanup(self):
        for mode in (0,5):
            self.c.reset(mode,0,0);self.c.sdio_wifi_scan()
            self.assertEqual([self.c.cache_state(i) for i in range(3)],[0,1,1])
        for mode in (1,2,3,4,6,7,8):
            self.c.reset(mode,0,0);self.c.sdio_wifi_scan()
            self.assertEqual([self.c.cache_state(i) for i in range(3)],[0,0,0])

    def test_completion_correlation(self):
        p = bytes([12, 0, 1, 0, 0x15, 0, 0, 0, 7, 0, 0, 0])
        self.assertEqual(self.c.wifi_scan_done(p, 12, 7), 1)
        for pos, value in [(0, 11), (2, 0), (4, 0x18), (8, 8)]:
            bad = bytearray(p); bad[pos] = value
            self.assertEqual(self.c.wifi_scan_done(bytes(bad), 12, 7), 0)
        self.assertEqual(self.c.wifi_scan_done(p, 11, 7), 0)

    def test_cancel_body_and_invalid_input(self):
        out = C.create_string_buffer(b'X'*12, 12)
        for cap, seq in ((11, 1), (12, 0), (12, 256)):
            self.assertEqual(self.c.wifi_scan_cancel(out, cap, seq), 0)
            self.assertEqual(out.raw, b'X'*12)
        self.assertEqual(self.c.wifi_scan_cancel(None, 12, 1), 0)
        self.assertEqual(self.c.wifi_scan_cancel(out, 12, 255), 12)
        self.assertEqual(out.raw, b'\0'*8 + b'\xff' + b'\0'*3)

    def test_timeout_cancels_matching_request_before_deactivation(self):
        for tick in (0, 0xfffffff0):
            self.c.reset(3, 0, tick)
            self.c.sdio_wifi_scan()
            self.assertEqual([self.c.step(i) for i in range(3)], [1, 2, 3])
            self.assertEqual(C.string_at(self.c.cancel_request(), 12), b'\0'*8 + b'\2\0\0\0')
            self.assertEqual((self.c.state(4), self.c.state(5), self.c.state(10), self.c.state(11)), (0, 1, 1, 1))
            before = self.states()
            self.c.sdio_wifi_scan()
            self.assertEqual(self.states()[:3], before[:3])
            self.assertEqual(self.c.state(7), 1)

    def test_uncertain_submission_mismatch_rx_and_cancel_failures_still_deactivate(self):
        for mode in (1, 2, 4, 8):
            self.c.reset(mode, 0, 0)
            self.c.sdio_wifi_scan()
            self.assertEqual([self.c.step(i) for i in range(3)], [1, 2, 3], mode)
            self.assertEqual((self.c.state(10), self.c.state(11), self.c.state(4)), (1, 1, 0), mode)

    def test_cancel_sequence_wrap_is_independent_of_command_header_sequence(self):
        self.c.reset(3, 0, 0)
        self.c.sequence(254)
        self.c.sdio_wifi_scan()
        self.assertEqual(C.string_at(self.c.cancel_request(), 12)[8], 1)

    def test_completed_scan_and_failed_activation_do_not_cancel(self):
        for mode in (0, 5, 6, 7):
            self.c.reset(mode, 0, 0)
            self.c.sdio_wifi_scan()
            self.assertEqual((self.c.state(10), self.c.state(11)), (0, 0), mode)

    def test_ap_start_guard_does_not_begin_radio_setup_on_unresolved_scan(self):
        self.c.reset(0, 0, 0)
        self.c.unresolved(1)
        self.c.sdio_wifi_ap()
        self.assertEqual(self.states()[:3], [0, 0, 0])
        self.c.unresolved(0)
        self.c.sdio_wifi_ap()
        self.assertEqual(self.c.state(2), 1)

    def test_actual_driver_activates_ais_drains_after_done_and_cleans_up(self):
        self.c.reset(0, 0, 0xfffffff0); self.c.sdio_wifi_scan()
        state = self.states()
        self.assertEqual(state[:3], [1, 1, 1])
        self.assertGreater(state[3], 2)  # read a beacon after RX1 scan-done
        self.assertEqual(state[4:], [1, 0, 0, 0, 0, 1])
        packet = C.string_at(self.c.request(), 120)
        self.assertEqual((packet[8], packet[9], packet[10], packet[11], packet[51]), (2, 0, 0, 1, 13))

    def test_failure_paths_cleanup_and_do_not_report_ready(self):
        for mode in (1, 2, 3, 4, 6, 7):
            self.c.reset(mode, 0, 0); self.c.sdio_wifi_scan()
            state = self.states()
            self.assertEqual(state[:2], [1, 1], mode)
            self.assertEqual((state[4], state[5], state[8]), (0, 1, 0), mode)

    def test_tail_has_a_bound_even_with_continuous_rx(self):
        self.c.reset(5, 0, 0); self.c.sdio_wifi_scan()
        state = self.states()
        self.assertEqual(state[:3], [1, 1, 1])
        self.assertEqual(state[4:9], [1, 0, 1, 0, 0])

    def test_active_ap_station_or_diagnostics_are_not_disturbed(self):
        for active in (1, 2, 4, 8, 16, 32):
            self.c.reset(0, active, 0); self.c.sdio_wifi_scan()
            self.assertEqual(self.states()[:3], [0, 0, 0])
            self.assertEqual(self.c.state(7), 1)


if __name__ == '__main__':
    unittest.main()
