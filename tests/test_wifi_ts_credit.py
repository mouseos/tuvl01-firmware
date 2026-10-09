"""Actual aggregate submission body: credit reservation and uncertain writes."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Credit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text()
        start=source.index('static unsigned ts_window_slots(')
        body=source[start:source.index('\nint sdio_wifi_ts(',start)]
        credit=source[source.index('static int data_credit('):source.index('/* Single SDIO owner only.',source.index('static int data_credit('))]
        harness=r'''
#include <stdint.h>
#include <string.h>
#include "wifi_ts_tx.h"
#include "wifi_tx_feedback.h"
#include "wifi_tx_timing.h"
static unsigned wifi_feedback_enabled,wifi_timing_enabled;
static struct wifi_tx_feedback wifi_feedback;
static struct wifi_tx_timing wifi_timing;
static uint8_t saved[3072];
static unsigned saved_length;
static uint32_t xTaskGetTickCount(void){return 42;}
#include "wifi_io_timing.h"
#include "wifi_raw_tx.h"
static unsigned raw_mode;
static unsigned sdio_wifi_raw_tx_selected(void){return raw_mode;}
static uint32_t board_time_counts(void){return 42;}
static struct wifi_io_timing wifi_io;

static unsigned wifi_ap_active=1,wifi_peer_active=1,wifi_tx_fault,wifi_tc1_free,wifi_data_tx,wifi_fixed54;
static unsigned wifi_ts_window=14,wifi_window_stalls,wifi_more_data;
static uint8_t wifi_mac[6],wifi_peer[6];
static int poll_result,write_result;
static unsigned polls,writes,packed_count,reserved_at_write;
static unsigned wifi_poll_reuse,wifi_credit_fresh,wifi_reuse_count;
static int tx_poll(void){polls++;wifi_credit_fresh=!poll_result;return poll_result;}
static unsigned pack(const uint8_t *d,unsigned n,unsigned s,unsigned i,unsigned f,
    const uint8_t *m,const uint8_t *p,uint8_t *o,unsigned cap,unsigned more){
    packed_count=n;return wifi_ts_tx_pack_forwarding(d,n,s,i,f,m,p,o,cap,more);
}
#define wifi_ts_tx_pack_forwarding pack
static int extended_write(unsigned a,const uint8_t *p,unsigned n,int inc){
    (void)a;(void)inc;memcpy(saved,p,n);saved_length=n;writes++;reserved_at_write=wifi_tc1_free;return write_result;
}
void reset(unsigned credits,int poll,int write){wifi_ts_window=14;wifi_window_stalls=0;wifi_tx_fault=wifi_data_tx=0;wifi_tc1_free=credits;
    polls=writes=packed_count=reserved_at_write=0;poll_result=poll;write_result=write;
    wifi_poll_reuse=wifi_credit_fresh=wifi_reuse_count=0;
    wifi_feedback_enabled=wifi_timing_enabled=wifi_fixed54=0;saved_length=0;
    memset(&wifi_feedback,0,sizeof wifi_feedback);wifi_tx_timing_reset(&wifi_timing);}
void window(unsigned n){wifi_ts_window=n;}
void cached(unsigned enabled,unsigned fresh){wifi_poll_reuse=enabled;wifi_credit_fresh=fresh;}
unsigned reused(void){return wifi_reuse_count;}
int send(unsigned n){static uint8_t d[14*188];return sdio_wifi_ts_pair(d,n,0,0,1);}
unsigned state(unsigned i){unsigned a[]={wifi_tc1_free,wifi_data_tx,wifi_tx_fault,polls,writes,packed_count,reserved_at_write};return a[i];}
int sampled(unsigned n,unsigned seq,unsigned fixed){
 static uint8_t d[14*188];wifi_feedback_enabled=wifi_timing_enabled=1;wifi_fixed54=fixed;
 return sdio_wifi_ts_pair(d,n,seq,0,1);
}
void fill_samples(void){memset(wifi_feedback.occupied,1,128);wifi_feedback.pending=128;}
unsigned feedback(unsigned i){unsigned a[]={wifi_feedback.requested,wifi_feedback.pending,wifi_feedback.cancelled,wifi_feedback.skipped,wifi_timing.sample_packets[0],wifi_feedback.sequence[0]};return a[i];}
const uint8_t *packet(void){return saved;}
unsigned length(void){return saved_length;}
'''
        # Function declaration precedes the wrapper; actual body follows stubs.
        prototype='int sdio_wifi_ts_pair(const unsigned char *,unsigned,unsigned,unsigned,unsigned);\n'
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'credit.c').write_text(prototype+harness+credit+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(p/'credit.c'),*[str(ROOT/'src'/n) for n in ['wifi_io_timing.c','wifi_raw_tx.c','wifi_ts_tx.c','wifi_net.c','wifi_tx_feedback.c','wifi_tx_timing.c']],'-o',str(p/'credit.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'credit.so'));cls.c.state.restype=ctypes.c_uint
        cls.c.packet.restype=ctypes.c_void_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def states(self):return [self.c.state(i) for i in range(7)]
    def test_sample_each_frame_and_preserve_rate_flag(self):
        for sequence,frame,count,recorded in [(0,0,7,0),(15,1,1,16),(0xffffffff,1,1,0)]:
            for fixed in (0,2):
                self.c.reset(14,0,0);self.assertEqual(self.c.sampled(8,sequence,fixed),8)
                wire=ctypes.string_at(self.c.packet(),self.c.length());offset=(int.from_bytes(wire[:2],'little')+3)&~3
                for f,start in enumerate((0,offset)):
                    self.assertEqual(wire[start+12],128 if f==frame else 0)
                    self.assertEqual(wire[start+13],(4 if fixed==2 else 0)|(1 if f==frame else 0))
                self.assertEqual([self.c.feedback(i) for i in range(6)],[1,1,0,0,count,recorded])
    def test_failed_aggregate_cancels_sample_without_credit_refund(self):
        self.c.reset(14,0,-1);self.assertEqual(self.c.sampled(14,0,0),-1)
        self.assertEqual(self.states()[:3],[12,0,1]);self.assertEqual([self.c.feedback(i) for i in range(5)],[1,0,1,0,0])
    def test_exhausted_sample_pool_does_not_block_transfer(self):
        self.c.reset(14,0,0);self.c.fill_samples();self.assertEqual(self.c.sampled(14,0,0),14)
        wire=ctypes.string_at(self.c.packet(),self.c.length());offset=(int.from_bytes(wire[:2],'little')+3)&~3
        self.assertEqual(wire[12:14]+wire[offset+12:offset+14],bytes(4))
        self.assertEqual([self.c.feedback(i) for i in range(4)],[0,128,0,1])
    def test_reserves_two_frames_before_write_and_handles_one_credit(self):
        self.c.reset(14,0,0);self.assertEqual(self.c.send(14),14)
        self.assertEqual(self.states(),[12,2,0,1,1,14,12])
        self.c.reset(1,0,0);self.assertEqual(self.c.send(14),7)
        self.assertEqual(self.states(),[0,1,0,1,1,7,0])
        self.c.reset(0,0,0);self.assertEqual(self.c.send(14),0)
        self.assertEqual(self.states(),[0,0,0,1,0,0,0])
    def test_uncertain_write_poison_does_not_refund_or_retry(self):
        self.c.reset(14,0,-1);self.assertEqual(self.c.send(14),-1)
        self.assertEqual(self.states(),[12,0,1,1,1,14,12])
        self.assertEqual(self.c.send(14),0)
        self.assertEqual(self.states(),[12,0,1,1,1,14,12])
    def test_aggregate_reuses_only_validated_positive_credit(self):
        self.c.reset(14,0,0);self.c.cached(1,1)
        for remaining in range(12,-1,-2):
            self.assertEqual(self.c.send(14),14)
            self.assertEqual(self.c.state(0),remaining)
        self.assertEqual(self.c.state(3),0)
        self.assertEqual(self.c.reused(),7)
        self.assertEqual(self.c.send(14),0)
        self.assertEqual(self.states()[:5],[0,14,0,1,7])
    def test_missing_cache_and_disabled_reuse_still_poll(self):
        for enabled,fresh in [(0,0),(0,1),(1,0)]:
            self.c.reset(14,-1,0);self.c.cached(enabled,fresh)
            self.assertEqual(self.c.send(14),-1)
            self.assertEqual(self.states(),[14,0,0,1,0,0,0])
    def test_cached_one_credit_and_window_reserve_exactly_once(self):
        self.c.reset(1,0,0);self.c.cached(1,1)
        self.assertEqual(self.c.send(14),7)
        self.assertEqual(self.states(),[0,1,0,0,1,7,0])
        self.c.reset(14,0,0);self.c.window(1);self.c.cached(1,1)
        self.assertEqual(self.c.send(14),7)
        self.assertEqual(self.c.send(14),0)
        self.assertEqual(self.states(),[13,1,0,0,1,7,13])
    def test_cached_uncertain_failure_stops_without_refund(self):
        self.c.reset(14,0,-1);self.c.cached(1,1)
        self.assertEqual(self.c.send(14),-1)
        self.assertEqual(self.states(),[12,0,1,0,1,14,12])
        self.assertEqual(self.c.send(14),0)
        self.assertEqual(self.states(),[12,0,1,0,1,14,12])
    def test_failed_poll_never_submits(self):
        self.c.reset(14,-1,0);self.assertEqual(self.c.send(14),-1)
        self.assertEqual(self.states(),[14,0,0,1,0,0,0])
    def test_window_counts_existing_outstanding_frames_and_never_refunds(self):
        for limit in (1,4,14):
            for free in range(15):
                self.c.reset(free,0,0);self.c.window(limit)
                result=self.c.send(14);state=self.states()
                held=14-free
                if held>=limit:
                    self.assertEqual(result,0)
                    self.assertEqual(state,[free,0,0,1,0,0,0])
                else:
                    frames=min(2,limit-held)
                    self.assertEqual(result,frames*7)
                    self.assertEqual(state,[free-frames,frames,0,1,1,frames*7,free-frames])
                    self.assertLessEqual(14-state[0],limit)
    def test_full_window_waits_for_returned_credit_before_next_submission(self):
        self.c.reset(14,0,0);self.c.window(1)
        self.assertEqual(self.c.send(14),7)
        self.assertEqual(self.c.send(14),0)
        self.assertEqual(self.states(),[13,1,0,2,1,7,13])
        self.c.reset(14,0,-1);self.c.window(1)
        self.assertEqual(self.c.send(14),-1)
        self.assertEqual(self.states(),[13,0,1,1,1,7,13])
    def test_invalid_credit_balance_does_not_submit(self):
        self.c.reset(15,0,0)
        self.assertEqual(self.c.send(14),0)
        self.assertEqual(self.states(),[15,0,0,1,0,0,0])
if __name__=='__main__':unittest.main()
