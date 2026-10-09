"""Actual submission bodies: per-frame rate flag and completion-bit coexistence."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Rate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text()
        start=source.index('static unsigned ts_window_slots(')
        actual=source[start:source.index('\nstatic int data_reply(',start)]
        harness=r'''
#include <stdint.h>
#include "wifi_io_timing.h"
#include "wifi_raw_tx.h"
#include "wifi_ht.h"
static unsigned wifi_ht_enabled;
static struct wifi_ht_peer wifi_peer_ht;
static unsigned raw_mode,wifi_qos_tc=1,wifi_tc2_free=1,wifi_tc3_free=1;
static unsigned sdio_wifi_raw_tx_selected(void){return raw_mode;}
static uint32_t board_time_counts(void){return 42;}
static struct wifi_io_timing wifi_io;
#include <string.h>
#include "wifi_ts_tx.h"
#include "wifi_net.h"
#include "wifi_tx_feedback.h"
#include "wifi_tx_timing.h"
static unsigned wifi_timing_enabled;
static struct wifi_tx_timing wifi_timing;
static uint32_t xTaskGetTickCount(void){return 42;}
static unsigned wifi_ap_active=1,wifi_peer_active=1,wifi_tx_fault,wifi_tc1_free=14,wifi_data_tx;
static unsigned wifi_fixed54,wifi_feedback_enabled,wifi_ts_window=14,wifi_window_stalls,wifi_more_data;
static uint8_t wifi_mac[6],wifi_peer[6],saved[3072];
static struct wifi_tx_feedback wifi_feedback;
static unsigned saved_length;
static int data_credit(unsigned n){(void)n;return 0;}
static int extended_write(unsigned a,const uint8_t *p,unsigned n,int inc){
    (void)a;(void)inc;memcpy(saved,p,n);saved_length=n;return 0;
}
static unsigned wifi_tx_feedback_reserve_stub(struct wifi_tx_feedback *p,unsigned s,uint8_t *tag){
    (void)p;(void)s;*tag=128;return 1;
}
static void wifi_tx_feedback_cancel_stub(struct wifi_tx_feedback *p,uint8_t tag){(void)p;(void)tag;}
#define wifi_tx_feedback_reserve wifi_tx_feedback_reserve_stub
#define wifi_tx_feedback_cancel wifi_tx_feedback_cancel_stub
'''
        wrappers=r'''
void raw(unsigned mode){raw_mode=mode;}
void more_data(unsigned selected){wifi_more_data=selected;}
void qos_class(unsigned tc){wifi_qos_tc=tc;}
void qos_peer(unsigned enabled,unsigned present,unsigned qos,unsigned mcs){wifi_ht_enabled=enabled;wifi_peer_ht.present=present;wifi_peer_ht.qos=qos;wifi_peer_ht.mcs=mcs;}
unsigned credit(void){return wifi_tc1_free;}
unsigned class_credit(unsigned tc){return tc==2?wifi_tc2_free:wifi_tc3_free;}
int again(void){static uint8_t d[7*188];return sdio_wifi_ts(d,7,1,7,0);}
int send(unsigned mode,unsigned feedback,unsigned count,unsigned pair){
    static uint8_t data[14*188];wifi_fixed54=mode;wifi_feedback_enabled=feedback;
    wifi_tc1_free=14;wifi_tc2_free=wifi_tc3_free=1;wifi_tx_fault=0;saved_length=0;
    return pair?sdio_wifi_ts_pair(data,count,0,0,1):sdio_wifi_ts(data,count,0,0,1);
}
int limited(unsigned free,unsigned window,unsigned pair){
    static uint8_t data[14*188];wifi_fixed54=0;wifi_feedback_enabled=0;
    wifi_tc1_free=free;wifi_ts_window=window;wifi_tx_fault=0;saved_length=0;
    int result=pair?sdio_wifi_ts_pair(data,14,0,0,1):sdio_wifi_ts(data,7,0,0,1);
    wifi_ts_window=14;return result;
}
const uint8_t *result(void){return saved;}
unsigned length(void){return saved_length;}
int timed(unsigned count){
    static uint8_t data[7*188];
    wifi_tx_timing_reset(&wifi_timing);wifi_timing_enabled=1;wifi_ts_window=1;
    wifi_fixed54=0;wifi_feedback_enabled=1;wifi_tc1_free=14;wifi_tx_fault=0;saved_length=0;
    int r=sdio_wifi_ts(data,count,0,0,1);wifi_timing_enabled=0;wifi_ts_window=14;return r;
}
unsigned timing(unsigned i){
    unsigned p=wifi_timing.packets;struct wifi_tx_time_bin *b=&wifi_timing.bin[p?p-1:0];
    unsigned v[]={wifi_timing.active,p,b->writes,b->write_sum,wifi_timing.sample_packets[0]};return v[i];
}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'rate.c').write_text(harness+actual+wrappers)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
            str(p/'rate.c'),str(ROOT/'src/wifi_ts_tx.c'),str(ROOT/'src/wifi_net.c'),str(ROOT/'src/wifi_tx_timing.c'),str(ROOT/'src/wifi_io_timing.c'),str(ROOT/'src/wifi_raw_tx.c'),str(ROOT/'src/wifi_ht.c'),'-o',str(p/'rate.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'rate.so'));cls.c.result.restype=ctypes.c_void_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_actual_pair_submission_marks_only_non_final_and_reserves_both_credits(self):
        self.c.more_data(1)
        try:
            for mode in (0,2):
                self.assertEqual(self.c.send(mode,0,14,1),14)
                b=ctypes.string_at(self.c.result(),self.c.length())
                first=(int.from_bytes(b[:2],'little')+3)&~3
                self.assertEqual(b[11],3);self.assertEqual(b[first+11],0x20)
                self.assertEqual(b[13],4 if mode==2 else 0)
                self.assertEqual(b[first+13],4 if mode==2 else 0)
                self.assertEqual(self.c.credit(),12)
            self.assertEqual(self.c.send(0,0,7,1),7)
            b=ctypes.string_at(self.c.result(),self.c.length())
            self.assertEqual(b[11],0x20);self.assertEqual(self.c.credit(),13)
        finally:self.c.more_data(0)
    def test_raw_actual_submission_and_aggregate_refusal(self):
        self.c.raw(1)
        try:
            self.assertEqual(self.c.send(0,1,7,0),1)
            b=ctypes.string_at(self.c.result(),self.c.length())
            self.assertEqual(b[2:6],bytes([23,4,24,0x90]));self.assertEqual(b[12:14],bytes([128,1]))
            self.assertEqual(b[16:18],bytes([8,2]));self.assertEqual(self.c.send(0,0,14,1),-1)
        finally:self.c.raw(0)
    def test_qos_submission_requires_negotiation_without_spending_credit(self):
        self.c.raw(2)
        try:
            for state in [(0,1,1,255),(1,0,1,255),(1,1,0,255),(1,1,1,0)]:
                self.c.qos_peer(*state);self.assertEqual(self.c.send(0,1,7,0),-1)
                self.assertEqual(self.c.length(),0);self.assertEqual(self.c.credit(),14)
            self.c.qos_peer(1,1,1,255);self.assertEqual(self.c.send(2,1,7,0),1)
            b=ctypes.string_at(self.c.result(),self.c.length());self.assertEqual(b[2:6],bytes([24,4,26,0x90]))
            self.assertEqual(b[12:14],bytes([128,5]));self.assertEqual(b[16:18],bytes([0x88,2]));self.assertEqual(b[40:42],bytes(2));self.assertEqual(self.c.credit(),13)
            self.assertEqual(self.c.send(0,0,14,1),-1)
        finally:self.c.raw(0);self.c.qos_peer(0,0,0,0)
    def test_qos_class_uses_own_single_credit_and_stalls_without_resend(self):
        self.c.raw(2);self.c.qos_peer(1,1,1,255)
        try:
            for tc,tid in [(2,4),(3,6)]:
                self.c.qos_class(tc);self.assertEqual(self.c.send(0,0,7,0),1)
                b=ctypes.string_at(self.c.result(),self.c.length());self.assertEqual(b[1]>>4,tid);self.assertEqual(b[3],tc<<2);self.assertEqual(b[40],tid)
                self.assertEqual(self.c.credit(),14);self.assertEqual(self.c.class_credit(tc),0);self.assertEqual(self.c.class_credit(5-tc),1)
                self.assertEqual(self.c.again(),0);self.assertEqual(self.c.credit(),14);self.assertEqual(self.c.class_credit(tc),0)
        finally:self.c.raw(0);self.c.qos_class(1);self.c.qos_peer(0,0,0,0)
    def test_single_frame_preserves_sampled_completion_bit(self):
        for mode in (0,1,2):
            for feedback in (0,1):
                self.assertEqual(self.c.send(mode,feedback,7,0),1)
                data=ctypes.string_at(self.c.result(),self.c.length())
                self.assertEqual(data[12],128 if feedback else 0)
                self.assertEqual(data[13],feedback|(4 if mode==2 else 0))
                self.assertEqual(data[16:22],bytes(6))
    def test_actual_submission_captures_size_write_and_callback_identity(self):
        for size in (1,3,7):
            self.assertEqual(self.c.timed(size),1)
            self.assertEqual([self.c.timing(i) for i in range(5)],[1,size,1,0,size])
    def test_each_aggregate_frame_is_modified_without_touching_padding(self):
        for mode in (0,1,2):
            for count in range(1,15):
                self.assertEqual(self.c.send(mode,0,count,1),count)
                data=ctypes.string_at(self.c.result(),self.c.length());offset=0;frames=0
                while data[offset:offset+4]!=bytes(4):
                    logical=int.from_bytes(data[offset:offset+2],'little')
                    self.assertEqual(data[offset+13],4 if mode==2 else 0)
                    aligned=(logical+3)&~3
                    self.assertEqual(data[offset+logical:offset+aligned],bytes(aligned-logical))
                    offset+=aligned;frames+=1
                self.assertEqual(frames,(count+6)//7)
                self.assertEqual(data[offset:],bytes(len(data)-offset))
    def test_single_and_aggregate_share_the_window_and_preserve_frame_contents(self):
        for window in (1,4,14):
            for free in range(15):
                for pair in (0,1):
                    remaining=window-(14-free)
                    result=self.c.limited(free,window,pair)
                    if remaining<=0:
                        self.assertEqual(result,0);self.assertEqual(self.c.length(),0)
                    else:
                        self.assertEqual(result,min(2,remaining)*7 if pair else 1)
                        data=ctypes.string_at(self.c.result(),self.c.length())
                        self.assertEqual(data[3],4)
                        first_is_last=not pair or result<=7
                        self.assertEqual(data[10:14],bytes([0,32 if first_is_last else 0,0,0]))
                        if pair and result>7:
                            second=(int.from_bytes(data[:2],'little')+3)&~3
                            self.assertEqual(data[second+10:second+14],bytes([0,32,0,0]))
