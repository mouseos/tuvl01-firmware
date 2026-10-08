"""Actual C fixed PER commands, idle guards and uncertain partial failure."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class PER(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=(ROOT/'src/sdio.c').read_text(encoding='utf-8');a=s.index('void sdio_wifi_auto_per(void){');b=s.index('void sdio_wifi_dpd(void){',a)
        harness=r"""
#include <stdint.h>
#include <string.h>
#include "wifi_fw_query.h"
static unsigned wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending,wifi_management_pending,wifi_data_count;
static unsigned wifi_per_attempted,wifi_per_transferred,wifi_per_steps,wifi_hif_ready,wifi_board_sent,wifi_tx_fault;
static unsigned wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc4_free,wifi_tc5_free;
static unsigned poll_error,fail_at,calls,stream;
static uint8_t saved[8][16];
static int tuner_ts_stream_active(void){return stream;}
static int tx_poll(void){return poll_error?-1:0;}
static void uart_puts(const char *s){(void)s;}
static void field(const char *s,uint32_t n){(void)s;(void)n;}
static int control_set(unsigned c,uint8_t *p,unsigned n){
 if(c!=0xc2 || n!=16 || calls>=8)return -1;
 memcpy(saved[calls],p,n);calls++;return calls==fail_at?-1:0;
}
void reset(unsigned mask,unsigned failure){
 wifi_ap_active=mask&1;wifi_peer_state=mask&2;wifi_peer_activate_pending=mask&4;
 wifi_management_pending=mask&8;wifi_data_count=mask&16;
 wifi_hif_ready=!(mask&32);wifi_board_sent=!(mask&64);wifi_tx_fault=mask&128;
 poll_error=mask&256;stream=mask&512;fail_at=failure;
 wifi_tc1_free=14;wifi_tc2_free=wifi_tc3_free=wifi_tc5_free=1;wifi_tc4_free=4;
 wifi_per_attempted=wifi_per_transferred=wifi_per_steps=calls=0;memset(saved,0xff,sizeof saved);
}
void pending(unsigned tc){switch(tc){case 1:wifi_tc1_free--;break;case 2:wifi_tc2_free--;break;case 3:wifi_tc3_free--;break;case 4:wifi_tc4_free--;break;case 5:wifi_tc5_free--;break;}}
unsigned result(unsigned n){unsigned v[]={calls,wifi_per_attempted,wifi_per_transferred,wifi_per_steps};return v[n];}
const uint8_t *packet(unsigned n){return saved[n];}
"""
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name);(p/'probe.c').write_text(harness+s[a:b],encoding='utf-8')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(p/'probe.c'),str(ROOT/'src/wifi_fw_query.c'),'-o',str(p/'probe.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'probe.so'));cls.c.packet.restype=ctypes.c_void_p
        cls.c.wifi_auto_per_command.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def state(self):return [self.c.result(n) for n in range(4)]
    def test_fixed_little_endian_commands_and_invalid_output_preservation(self):
        values=[1,0x850000,1,0x870000,0,0x9c0000,0,0x9d0000]
        for step,value in enumerate(values):
            buf=(ctypes.c_ubyte*24)(*([0xa5]*24));self.assertEqual(self.c.wifi_auto_per_command(buf,24,step),16)
            expected=bytes(8)+(0x90000100+(0 if step%2 else 4)).to_bytes(4,'little')+value.to_bytes(4,'little')
            self.assertEqual(bytes(buf),expected+b'\xa5'*8)
        for capacity,step in ((15,0),(24,8),(24,0xffffffff)):
            buf=(ctypes.c_ubyte*24)(*([0xa5]*24));self.assertEqual(self.c.wifi_auto_per_command(buf,capacity,step),0);self.assertEqual(bytes(buf),b'\xa5'*24)
        self.assertEqual(self.c.wifi_auto_per_command(None,24,0),0)
    def test_active_unready_fault_and_credit_guards_do_not_consume_attempt(self):
        for mask in (1,2,4,8,16,32,64,128,256,512):
            self.c.reset(mask,0);self.c.sdio_wifi_auto_per();self.assertEqual(self.state(),[0,0,0,0])
        for tc in range(1,6):
            self.c.reset(0,0);self.c.pending(tc);self.c.sdio_wifi_auto_per();self.assertEqual(self.state(),[0,0,0,0])
    def test_actual_complete_sequence_and_one_shot(self):
        self.c.reset(0,0);self.c.sdio_wifi_auto_per();self.assertEqual(self.state(),[8,1,1,8])
        for step in range(8):
            expected=(ctypes.c_ubyte*16)();self.c.wifi_auto_per_command(expected,16,step)
            self.assertEqual(ctypes.string_at(self.c.packet(step),16),bytes(expected))
        self.c.sdio_wifi_auto_per();self.assertEqual(self.state(),[8,1,1,8])
    def test_each_uncertain_failure_stops_without_retry_or_false_success(self):
        for fail in range(1,9):
            self.c.reset(0,fail);self.c.sdio_wifi_auto_per();self.assertEqual(self.state(),[fail,1,0,fail-1])
            self.c.sdio_wifi_auto_per();self.assertEqual(self.state(),[fail,1,0,fail-1])
if __name__=='__main__':unittest.main()
