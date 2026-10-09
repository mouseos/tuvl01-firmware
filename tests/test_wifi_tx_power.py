import ctypes as C
import pathlib, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class TxPower(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        text=(ROOT/'src/sdio.c').read_text()
        body=text[text.index('void sdio_wifi_tx_power(void){'):text.index('void sdio_wifi_osc(void){')]
        harness=r'''
#include <stdint.h>
#include "wifi_tx_power.h"
static unsigned wifi_tx_power_step,wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending;
static unsigned wifi_management_pending,wifi_data_count,wifi_ais_retained_active,wifi_connection_unresolved;
static unsigned wifi_hif_ready,wifi_board_sent,wifi_tx_fault,wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc4_free,wifi_tc5_free;
static unsigned streaming,poll_fail,send_fail,calls,cid,length;
static uint8_t wire[40];
static int tuner_ts_stream_active(void){return streaming;}
static int tx_poll(void){return poll_fail;}
static void uart_puts(const char *s){(void)s;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static int control_set(unsigned c,uint8_t *p,unsigned n){
    calls++;cid=c;length=n;for(unsigned i=0;i<n && i<40;i++)wire[i]=p[i];return send_fail;
}
void reset(unsigned bad){
    wifi_tx_power_step=calls=cid=length=0;
    wifi_ap_active=bad&1;wifi_peer_state=bad&2;wifi_peer_activate_pending=bad&4;
    wifi_management_pending=bad&8;wifi_data_count=bad&16;streaming=bad&32;
    wifi_ais_retained_active=bad&64;wifi_connection_unresolved=bad&128;
    wifi_hif_ready=!(bad&256);wifi_board_sent=!(bad&512);wifi_tx_fault=bad&1024;
    poll_fail=bad&2048;wifi_tc1_free=bad&4096?13:14;wifi_tc2_free=bad&8192?0:1;
    wifi_tc3_free=bad&16384?0:1;wifi_tc4_free=bad&32768?3:4;
    wifi_tc5_free=bad&65536?0:1;send_fail=bad&131072;
}
unsigned state(unsigned n){unsigned v[]={calls,cid,length,wifi_tx_power_step,wifi_connection_unresolved};return v[n];}
unsigned byte(unsigned n){return wire[n];}
'''
        (p/'h.c').write_text(harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(p/'h.c'),str(ROOT/'src/wifi_tx_power.c'),
            '-o',str(p/'h.so')],check=True)
        cls.c=C.CDLL(str(p/'h.so'))
        cls.c.wifi_tx_power_command.argtypes=[C.c_void_p,C.c_uint,C.c_int]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_wire_roles_defaults_reserved_and_tail(self):
        for offset in (0,-12,-24):
            out=(C.c_uint8*48)(*([165]*48))
            self.assertEqual(self.c.wifi_tx_power_command(out,48,offset),1)
            expected=bytes(8)+bytes([offset&255])*4+bytes(8)+bytes([63])*18+bytes(2)
            self.assertEqual(bytes(out[:40]),expected)
            self.assertEqual(bytes(out[40:]),bytes([165])*8)
    def test_invalid_requests_preserve_output(self):
        for cap,offset in ((39,0),(40,1),(40,-1),(40,-25),(40,127),(40,-128)):
            out=(C.c_uint8*40)(*([165]*40))
            self.assertEqual(self.c.wifi_tx_power_command(out,cap,offset),0)
            self.assertEqual(bytes(out),bytes([165])*40)
        self.assertEqual(self.c.wifi_tx_power_command(None,40,0),0)
    def test_active_state_and_every_credit_guard(self):
        for bit in range(17):
            self.c.reset(1<<bit);self.c.sdio_wifi_tx_power()
            self.assertEqual(self.c.state(0),0)
            self.assertEqual(self.c.state(3),0)
    def test_transfer_cycle_and_failure_latch(self):
        self.c.reset(0)
        for step,offset in ((1,-12),(2,-24),(0,0)):
            self.c.sdio_wifi_tx_power()
            self.assertEqual([self.c.state(i) for i in (1,2,3,4)],[0x38,40,step,0])
            self.assertEqual(self.c.byte(8),offset&255)
        self.c.reset(131072);self.c.sdio_wifi_tx_power()
        self.assertEqual([self.c.state(i) for i in (0,3,4)],[1,0,1])
        self.c.sdio_wifi_tx_power();self.assertEqual(self.c.state(0),1)

if __name__=='__main__':unittest.main()
