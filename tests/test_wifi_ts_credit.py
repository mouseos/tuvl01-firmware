"""Actual aggregate submission body: credit reservation and uncertain writes."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Credit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text()
        start=source.index('static unsigned ts_window_slots(')
        body=source[start:source.index('\nint sdio_wifi_ts(',start)]
        harness=r'''
#include <stdint.h>
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
static int tx_poll(void){polls++;return poll_result;}
static unsigned wifi_ts_tx_pack_forwarding(const uint8_t *d,unsigned n,unsigned s,unsigned i,unsigned f,
    const uint8_t *m,const uint8_t *p,uint8_t *o,unsigned cap,unsigned more){
    (void)more;(void)d;(void)s;(void)i;(void)f;(void)m;(void)p;(void)o;(void)cap;packed_count=n;return 3072;
}
static int extended_write(unsigned a,const uint8_t *p,unsigned n,int inc){
    (void)a;(void)p;(void)n;(void)inc;writes++;reserved_at_write=wifi_tc1_free;return write_result;
}
void reset(unsigned credits,int poll,int write){wifi_ts_window=14;wifi_window_stalls=0;wifi_tx_fault=wifi_data_tx=0;wifi_tc1_free=credits;
    polls=writes=packed_count=reserved_at_write=0;poll_result=poll;write_result=write;}
void window(unsigned n){wifi_ts_window=n;}
int send(unsigned n){static uint8_t d[14*188];return sdio_wifi_ts_pair(d,n,0,0,1);}
unsigned state(unsigned i){unsigned a[]={wifi_tc1_free,wifi_data_tx,wifi_tx_fault,polls,writes,packed_count,reserved_at_write};return a[i];}
'''
        # Function declaration precedes the wrapper; actual body follows stubs.
        prototype='int sdio_wifi_ts_pair(const unsigned char *,unsigned,unsigned,unsigned,unsigned);\n'
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'credit.c').write_text(prototype+harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(p/'credit.c'),str(ROOT/'src/wifi_io_timing.c'),str(ROOT/'src/wifi_raw_tx.c'),'-o',str(p/'credit.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'credit.so'));cls.c.state.restype=ctypes.c_uint
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def states(self):return [self.c.state(i) for i in range(7)]
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
