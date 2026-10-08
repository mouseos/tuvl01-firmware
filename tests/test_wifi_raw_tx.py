"""Native From-DS address/LLC/HIF mapping, sequence wrap and rejection guards."""
import ctypes as C,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Raw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        source=(ROOT/'src/sdio.c').read_text(encoding='utf-8');a=source.index('unsigned sdio_wifi_raw_tx_selected(void){');b=source.index('void sdio_wifi_ht(void){',a)
        harness=r'''#include <stdint.h>
#include "wifi_tx_feedback.h"
static struct wifi_tx_feedback wifi_feedback;
static unsigned wifi_hif_ready=1,wifi_tx_fault,wifi_tc1_free=14,wifi_tc2_free=1,wifi_tc3_free=1,wifi_timing_enabled,wifi_qos_tc=1;
static unsigned wifi_fixed54,wifi_fixed_mcs;
static unsigned wifi_ht_enabled,wifi_raw_tx_mode,wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending,stream,aggregate;
static int tuner_ts_stream_active(void){return stream;}
static int tuner_ts_stream_aggregate_active(void){return aggregate;}
static void uart_puts(const char *s){(void)s;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
void state(unsigned mask,unsigned agg){wifi_ap_active=mask&1;wifi_peer_state=mask&2;wifi_peer_activate_pending=mask&4;stream=mask&8;aggregate=agg;wifi_raw_tx_mode=0;wifi_ht_enabled=0;wifi_qos_tc=1;wifi_tc1_free=14;wifi_tc2_free=wifi_tc3_free=1;wifi_timing_enabled=0;wifi_tx_fault=0;wifi_hif_ready=1;wifi_feedback.pending=0;}
void credit(unsigned tc,unsigned n){if(tc==2)wifi_tc2_free=n;else wifi_tc3_free=n;}
void busy(unsigned n){wifi_ap_active=n;}
void ht(unsigned n){wifi_ht_enabled=n;}
'''
        (p/'guard.c').write_text(harness+source[a:b],encoding='utf-8')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/wifi_raw_tx.c'),str(p/'guard.c'),'-o',str(p/'raw.so')],check=True)
        cls.c=C.CDLL(str(p/'raw.so'));cls.c.wifi_raw_tx_pack.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.c_void_p,C.c_uint]
        cls.c.wifi_raw_qos_tx_pack.argtypes=cls.c.wifi_raw_tx_pack.argtypes
        cls.c.wifi_raw_qos_class_tx_pack.argtypes=cls.c.wifi_raw_tx_pack.argtypes+[C.c_uint,C.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def eth(self,length):return bytes.fromhex('0211223344550266778899aa0800')+bytes(i&255 for i in range(length-14))
    def pack(self,length=1374,sequence=0x1234,capacity=2048):
        e=self.eth(length);m=bytes.fromhex('02aabbccddee');o=C.create_string_buffer(bytes([0x5a])*2048,2048)
        n=self.c.wifi_raw_tx_pack(e,len(e),m,sequence,o,capacity);return e,m,n,o.raw
    def test_address_and_llc_mapping_preserves_payload(self):
        e,m,n,b=self.pack();self.assertEqual(n,1536);logical=int.from_bytes(b[:2],'little');self.assertEqual(logical,1408)
        self.assertEqual(b[2:6],bytes([23,4,24,0x90]));self.assertEqual(b[10:14],bytes([0,0x20,0,0]))
        f=b[16:logical];self.assertEqual(f[:4],bytes([8,2,0,0]));self.assertEqual((f[4:10],f[10:16],f[16:22]),(e[:6],m,e[6:12]))
        self.assertEqual(f[22:24],bytes.fromhex('4023'));self.assertEqual(f[24:32],bytes.fromhex('aaaa030000000800'));self.assertEqual(f[32:],e[14:]);self.assertEqual(b[logical:n],bytes(n-logical))
    def test_padding_boundary_and_sequence_wrap(self):
        for length,n in [(14,48),(478,512),(479,1024),(1514,2048)]:
            e,m,z,b=self.pack(length,0x1000);self.assertEqual(z,n);self.assertEqual(b[38:40],bytes(2))
        e,m,n,b=self.pack(1374,0xfff);self.assertEqual(b[38:40],bytes.fromhex('f0ff'))
    def test_invalid_and_overlap_do_not_modify_output(self):
        e,m,n,b=self.pack(capacity=1535);self.assertEqual(n,0);self.assertEqual(b,bytes([0x5a])*2048)
        for length in [13,1515]:
            e=self.eth(max(length,14));o=C.create_string_buffer(bytes([0x5a])*2048,2048)
            self.assertEqual(self.c.wifi_raw_tx_pack(e,length,m,0,o,2048),0);self.assertEqual(o.raw,bytes([0x5a])*2048)
        for offset in [0,6]:
            e=bytearray(self.eth(60));e[offset]|=1;o=C.create_string_buffer(bytes([0x5a])*2048,2048)
            self.assertEqual(self.c.wifi_raw_tx_pack(bytes(e),60,m,0,o,2048),0)
        o=C.create_string_buffer(self.eth(60)+bytes(1988),2048);before=o.raw
        self.assertEqual(self.c.wifi_raw_tx_pack(o,60,m,0,o,2048),0);self.assertEqual(o.raw,before)
        self.assertEqual(self.c.wifi_raw_tx_pack(self.eth(60),60,o,0,o,2048),0);self.assertEqual(o.raw,before)
    def test_actual_selector_rejects_active_and_aggregate_states(self):
        for mask in [1,2,4,8,15]:
            self.c.state(mask,0);self.c.sdio_wifi_raw_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),0)
        self.c.state(0,1);self.c.sdio_wifi_raw_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),0)
        self.c.state(0,0);self.c.sdio_wifi_raw_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),1);self.c.sdio_wifi_raw_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),0)
    def test_qos_mac_llc_and_padding_boundaries(self):
        for length,expected in [(14,52),(476,512),(477,1024),(1374,1536),(1514,2048)]:
            e=self.eth(length);m=bytes.fromhex('02aabbccddee');o=C.create_string_buffer(2048)
            n=self.c.wifi_raw_qos_tx_pack(e,length,m,0xfff,o,2048);b=o.raw;logical=int.from_bytes(b[:2],'little')
            self.assertEqual(n,expected);self.assertEqual(logical,length+36)
            self.assertEqual(b[2:6],bytes([24,4,26,0x90]));self.assertEqual(b[16:20],bytes([0x88,2,0,0]))
            self.assertEqual(b[20:38],e[:6]+m+e[6:12]);self.assertEqual(b[38:42],bytes.fromhex('f0ff0000'))
            self.assertEqual(b[42:50],bytes.fromhex('aaaa030000000800'));self.assertEqual(b[50:logical],e[14:]);self.assertEqual(b[logical:n],bytes(n-logical))
    def test_qos_selector_requires_ht_native_and_idle(self):
        self.c.state(0,0);self.c.ht(1);self.c.sdio_wifi_qos_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),0)
        self.c.sdio_wifi_raw_tx();self.c.ht(0);self.c.sdio_wifi_qos_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),1)
        self.c.ht(1);self.c.sdio_wifi_qos_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),2)
        self.c.sdio_wifi_qos_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),1)
        self.c.sdio_wifi_qos_tx();self.c.sdio_wifi_raw_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),0)
        for mask in [1,2,4,8]:
            self.c.state(mask,0);self.c.ht(1);self.c.sdio_wifi_qos_tx();self.assertEqual(self.c.sdio_wifi_raw_tx_selected(),0)
    def test_matched_priority_class_mapping_and_invalid_pairs(self):
        e=self.eth(1374);m=bytes.fromhex('02aabbccddee')
        for tid,tc in [(0,1),(4,2),(6,3)]:
            o=C.create_string_buffer(2048);n=self.c.wifi_raw_qos_class_tx_pack(e,len(e),m,0,o,2048,tid,tc);b=o.raw
            self.assertEqual(n,1536);self.assertEqual(int.from_bytes(b[:2],'little')&4095,1410)
            self.assertEqual(b[1]>>4,tid);self.assertEqual(b[3],tc<<2);self.assertEqual(b[40:42],bytes([tid,0]));self.assertEqual(b[50:1410],e[14:])
        for tid,tc in [(0,2),(4,1),(6,2),(8,3),(6,4),(0,0)]:
            o=C.create_string_buffer(bytes([90])*2048,2048);self.assertEqual(self.c.wifi_raw_qos_class_tx_pack(e,len(e),m,0,o,2048,tid,tc),0);self.assertEqual(o.raw,bytes([90])*2048)
    def test_class_cycle_refuses_unreturned_credit_and_active_state(self):
        self.c.state(0,0);self.c.ht(1);self.c.sdio_wifi_raw_tx();self.c.sdio_wifi_qos_tx()
        for expected in [2,3,1]:
            self.c.sdio_wifi_qos_class();self.assertEqual(self.c.sdio_wifi_qos_class_selected(),expected)
        self.c.credit(2,0);self.c.sdio_wifi_qos_class();self.assertEqual(self.c.sdio_wifi_qos_class_selected(),1)
        self.c.credit(2,1);self.c.credit(3,0);self.c.sdio_wifi_qos_class();self.assertEqual(self.c.sdio_wifi_qos_class_selected(),1)
        self.c.credit(3,1);self.c.busy(1);self.c.sdio_wifi_qos_class();self.assertEqual(self.c.sdio_wifi_qos_class_selected(),1)
        self.c.busy(0);self.c.sdio_wifi_qos_class();self.assertEqual(self.c.sdio_wifi_qos_class_selected(),2)
        self.c.sdio_wifi_raw_tx();self.assertEqual(self.c.sdio_wifi_qos_class_selected(),1)
if __name__=='__main__':unittest.main()
