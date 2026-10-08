"""Actual-C MT5931 wire decoder and read-clear credit accounting."""
import ctypes,pathlib,struct,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Status(ctypes.Structure):
    _fields_=[(n,ctypes.c_uint32) for n in ('interrupt','tx0','tx1','rx_lengths','mailbox0','mailbox1')]
class Decode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
            str(ROOT/'src/wifi_status.c'),str(ROOT/'src/wifi_io_timing.c'),'-o',str(p/'decode.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'decode.so'));cls.c.wifi_status_decode.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(Status)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_little_endian_layout_and_stale_interrupt_correction(self):
        b=bytearray(88);struct.pack_into('<IIIHH',b,0,4,0x00000100,0x00000101,1,1)
        struct.pack_into('<H',b,16,4092);struct.pack_into('<H',b,48,4096)
        struct.pack_into('<II',b,80,0x12345678,0x90abcdef)
        out=Status();self.assertEqual(self.c.wifi_status_decode(bytes(b),88,ctypes.byref(out)),1)
        self.assertEqual([getattr(out,n) for n,_ in Status._fields_],[5,256,257,4092|(4096<<16),0x12345678,0x90abcdef])
    def test_unused_slots_and_mailboxes_do_not_invent_tx_interrupt(self):
        b=bytearray(b'\xa5'*88);b[:16]=bytes(16)
        out=Status();self.assertEqual(self.c.wifi_status_decode(bytes(b),88,ctypes.byref(out)),1)
        self.assertEqual((out.interrupt,out.rx_lengths),(0,0))
    def test_invalid_lengths_counts_and_null_preserve_output(self):
        cases=[]
        for offset,value in ((12,2),(14,16),(16,7),(16,4093),(48,0),(48,4097)):
            b=bytearray(88);struct.pack_into('<HH',b,12,1,1)
            struct.pack_into('<H',b,16,12);struct.pack_into('<H',b,48,20)
            struct.pack_into('<H',b,offset,value);cases.append((bytes(b),88))
        cases.extend([(bytes(88),87),(bytes(89),89),(None,88)])
        for b,n in cases:
            out=Status(*([0xdeadbeef]*6))
            self.assertEqual(self.c.wifi_status_decode(b,n,ctypes.byref(out)),0)
            self.assertEqual(bytes(out),struct.pack('=6I',*([0xdeadbeef]*6)))
        self.assertEqual(self.c.wifi_status_decode(bytes(88),88,None),0)
class Poll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text();start=source.index('static int tx_poll(void){')
        actual=source[start:source.index('\nstatic int data_credit',start)]
        start=source.index('static int event_read(uint8_t *packet,unsigned capacity,unsigned *length){')
        header=source[start:source.index('    unsigned read_length=',start)]
        header=header.replace('static int event_read(','static int event_header(')
        header+='    (void)packet;(void)capacity;(void)port;return 0;\n}\n'
        harness=r'''
#include <stdint.h>
#include "wifi_io_timing.h"
static uint32_t board_time_counts(void){return 42;}
static struct wifi_io_timing wifi_io;
#include <string.h>
#include "wifi_status.h"
#include "wifi_tx_timing.h"
static struct wifi_tx_timing wifi_timing;
static unsigned wifi_timing_enabled;
static uint32_t xTaskGetTickCount(void){return 42;}
static unsigned wifi_status_polling,wifi_status_reads,wifi_credit_fresh,wifi_poll_count;
static unsigned wifi_credit_probe,wifi_probe_reads,wifi_probe_released;
static unsigned wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending;
static uint32_t wifi_status_rx;
static unsigned wifi_tc2_free,wifi_tc3_free;
static unsigned wifi_tx_fault,wifi_hif_ready=1,wifi_verbose,wifi_tc4_free,wifi_tc1_free,wifi_tc5_free;
static uint8_t response[88];static unsigned reads,words,failed,invalid,legacy_phase;
static int fifo_read(unsigned a,uint8_t *b,unsigned n){
    if(a!=16 || n!=88)return -1;
    reads++;if(failed)return -1;
    memcpy(b,response,88);memset(response+4,0,8);return 0;
}
static uint32_t irq_word,tx0_word,tx1_word;static unsigned fail_address;
static int radio_read(unsigned a,uint32_t *v){
    words++;if(a==fail_address)return -1;
    if(a==16)*v=irq_word;else if(a==32){*v=tx0_word;tx0_word=0;legacy_phase++;}
    else if(a==36){*v=tx1_word;tx1_word=0;}
    else if(a==80)*v=12|(20<<16);
    else *v=0;
    return 0;
}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static void uart_puts(const char *s){(void)s;}
void probe(unsigned mode){wifi_credit_probe=mode;irq_word=0;}
void regfail(unsigned address){fail_address=address;}
void idle(void){wifi_tc1_free=14;wifi_tc4_free=4;}
void guard(unsigned mask){wifi_ap_active=mask&1;wifi_peer_state=mask&2;wifi_peer_activate_pending=mask&4;}
unsigned probes(unsigned n){unsigned v[]={wifi_credit_probe,wifi_probe_reads,wifi_probe_released};return v[n];}
void reset(unsigned mode,unsigned fail){
    irq_word=1;tx0_word=256;tx1_word=1;fail_address=0;
    wifi_credit_probe=wifi_probe_reads=wifi_probe_released=0;
    wifi_ap_active=wifi_peer_state=wifi_peer_activate_pending=0;
    memset(response,0,88);response[5]=1;response[8]=1;response[12]=1;response[14]=1;
    response[16]=12;response[48]=20;wifi_status_polling=mode;failed=fail;
    wifi_tc4_free=3;wifi_tc1_free=13;wifi_tc5_free=1;wifi_tc2_free=wifi_tc3_free=1;
    wifi_credit_fresh=wifi_poll_count=wifi_tx_fault=wifi_status_reads=wifi_status_rx=reads=words=invalid=legacy_phase=0;
}
void corrupt(void){response[12]=2;}
void timed(void){wifi_timing_enabled=1;wifi_tx_timing_reset(&wifi_timing);wifi_tx_timing_begin(&wifi_timing,7,40);}
unsigned timing(unsigned n){unsigned v[]={wifi_timing.bin[6].poll_sum,wifi_timing.bin[6].poll_gap_max,wifi_timing.bin[6].credits};return v[n];}
void overflow(void){response[5]=2;}
void qos_release(unsigned tc,unsigned n,unsigned free){response[4+tc]=n;if(tc==2)wifi_tc2_free=free;else wifi_tc3_free=free;}
unsigned qos_free(unsigned tc){return tc==2?wifi_tc2_free:wifi_tc3_free;}
unsigned state(unsigned n){unsigned v[]={wifi_tc4_free,wifi_tc1_free,wifi_tc5_free,wifi_tx_fault,
    wifi_credit_fresh,wifi_status_rx,reads,words};return v[n];}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        start=source.index('void sdio_wifi_credit_probe(void){')
        selector=source[start:source.index('void sdio_wifi_status_poll(void){',start)]
        (p/'poll.c').write_text(harness+actual+selector+header+'\nint poll(void){return tx_poll();}\n'
            'int header(void){uint8_t p[4];unsigned n=0;int r=event_header(p,4,&n);return r<0?-1:(int)n;}\n')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
            str(p/'poll.c'),str(ROOT/'src/wifi_status.c'),str(ROOT/'src/wifi_tx_timing.c'),str(ROOT/'src/wifi_io_timing.c'),'-o',str(p/'poll.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'poll.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def states(self):return [self.c.state(i) for i in range(8)]
    def test_snapshot_accounts_stale_bit_releases_once_without_register_reads(self):
        self.c.reset(1,0);self.assertEqual(self.c.poll(),0)
        self.assertEqual(self.states(),[4,14,1,0,1,12|(20<<16),1,0])
        self.assertEqual(self.c.poll(),0)
        self.assertEqual(self.states(),[4,14,1,0,1,12|(20<<16),2,0])
    def test_original_mode_keeps_original_three_register_reads(self):
        self.c.reset(0,0);self.assertEqual(self.c.poll(),0)
        self.assertEqual(self.states(),[4,14,1,0,1,0,0,3])
    def test_probe_reads_without_irq_and_consumes_once(self):
        self.c.reset(0,0);self.c.probe(0);self.assertEqual(self.c.poll(),0)
        self.assertEqual(self.states(),[3,13,1,0,1,0,0,1])
        self.c.probe(1);self.assertEqual(self.c.poll(),0)
        self.assertEqual(self.states(),[4,14,1,0,1,0,0,4])
        self.assertEqual([self.c.probes(i) for i in range(3)],[1,1,2])
        self.assertEqual(self.c.poll(),0);self.assertEqual(self.c.state(7),5)
        self.assertEqual(self.c.probes(2),2)
    def test_probe_partial_read_failure_poison_never_grants(self):
        for address in (32,36):
            self.c.reset(0,0);self.c.probe(1);self.c.regfail(address)
            self.assertEqual(self.c.poll(),-1)
            self.assertEqual([self.c.state(i) for i in (0,1,3,4)],[3,13,1,0])
            self.assertEqual(self.c.probes(2),0)
    def test_probe_selector_refuses_active_snapshot_or_unreturned_credits(self):
        for mask in (1,2,4):
            self.c.reset(0,0);self.c.guard(mask);self.c.sdio_wifi_credit_probe()
            self.assertEqual(self.c.probes(0),0);self.assertEqual(self.c.state(7),0)
        self.c.reset(1,0);self.c.idle();self.c.sdio_wifi_credit_probe()
        self.assertEqual(self.c.probes(0),0)
        self.c.reset(0,0);self.c.probe(0);self.c.sdio_wifi_credit_probe()
        self.assertEqual(self.c.probes(0),0)
        self.c.reset(0,0);self.c.poll();self.c.sdio_wifi_credit_probe()
        self.assertEqual(self.c.probes(0),1)
        self.c.sdio_wifi_credit_probe();self.assertEqual(self.c.probes(0),0)
    def test_successful_status_observation_reaches_active_timing_sample(self):
        self.c.reset(0,0);self.c.timed();self.assertEqual(self.c.poll(),0)
        self.assertEqual([self.c.timing(i) for i in range(3)],[1,2,1])
    def test_event_header_uses_fresh_snapshot_without_second_length_read(self):
        self.c.reset(1,0);self.assertEqual(self.c.header(),20)
        self.assertEqual(self.states(),[4,14,1,0,1,12|(20<<16),1,0])
        self.c.reset(0,0);self.assertEqual(self.c.header(),20)
        self.assertEqual(self.states(),[4,14,1,0,1,0,0,4])
    def test_uncertain_read_and_invalid_layout_stop_without_granting_credit(self):
        self.c.reset(1,1);self.assertEqual(self.c.poll(),-1)
        self.assertEqual(self.states(),[3,13,1,1,0,0,1,0])
        self.c.reset(1,0);self.c.corrupt();self.assertEqual(self.c.poll(),-1)
        self.assertEqual(self.states(),[3,13,1,1,0,0,1,0])
    def test_excess_release_poisons_tx(self):
        self.c.reset(1,0);self.c.overflow();self.assertEqual(self.c.poll(),-1)
        self.assertEqual(self.c.state(3),1);self.assertEqual(self.c.state(4),0)
    def test_qos_release_is_isolated_read_clear_and_overflow_poisoned(self):
        for tc in [2,3]:
            self.c.reset(1,0);self.c.qos_release(tc,1,0);self.assertEqual(self.c.poll(),0)
            self.assertEqual(self.c.qos_free(tc),1);self.assertEqual(self.c.qos_free(5-tc),1)
            self.assertEqual(self.c.poll(),0);self.assertEqual(self.c.qos_free(tc),1)
            self.c.reset(1,0);self.c.qos_release(tc,1,1);self.assertEqual(self.c.poll(),-1)
            self.assertEqual(self.c.state(3),1);self.assertEqual(self.c.qos_free(tc),1)
if __name__=='__main__':unittest.main()
