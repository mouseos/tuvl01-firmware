"""Exercise actual board-driver TC4 helpers with controlled SDIO failures."""
import ctypes
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TC4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'src/sdio.c').read_text()
        start = source.index('static int tc4_wait(void){')
        body = source[start:source.index('static int control_send(', start)]
        harness = r'''
#include <stdint.h>
typedef uint32_t TickType_t;
static unsigned wifi_hif_ready,wifi_tx_fault,wifi_tc4_free;
static unsigned wifi_connection_unresolved;
static unsigned wifi_mac_valid,wifi_ap_active,wifi_peer_state;
static uint8_t wifi_mac[6];
static struct { unsigned watch,activated,beacon_seen,aid;struct {uint8_t ap[6];} selected;} wifi_ais_connection;
static unsigned polls,writes,reserved,delays,release_at,write_port;
static int poll_result,write_result;
static uint32_t ticks;
static void uart_puts(const char *s){(void)s;}
static TickType_t xTaskGetTickCount(void){return ticks;}
static void vTaskDelay(unsigned n){ticks+=n;delays++;}
static int tx_poll(void){polls++;if(release_at && polls==release_at)wifi_tc4_free=1;return poll_result;}
static int extended_write(unsigned port,const uint8_t *p,unsigned n,int inc){
    (void)p;(void)n;(void)inc;writes++;write_port=port;reserved=wifi_tc4_free;return write_result;
}
'''
        wrappers = r'''
void reset(unsigned ready,unsigned credits,int poll,int write,unsigned release,uint32_t tick){
    wifi_hif_ready=ready;wifi_tc4_free=credits;wifi_tx_fault=0;
    wifi_connection_unresolved=0;
    polls=writes=reserved=delays=write_port=0;poll_result=poll;write_result=write;
    release_at=release;ticks=tick;
}
int wait_credit(void){return tc4_wait();}
void unresolved(unsigned n){wifi_connection_unresolved=n;}
int submit(const uint8_t *p,unsigned n){return tc4_write(p,n);}
void wpa_ready(unsigned missing){
    wifi_mac_valid=!(missing&1);wifi_ap_active=!!(missing&2);wifi_peer_state=!!(missing&4);
    wifi_ais_connection.watch=!(missing&8);wifi_ais_connection.activated=!(missing&16);
    wifi_ais_connection.beacon_seen=!(missing&32);wifi_ais_connection.aid=!(missing&64);
    for(unsigned i=0;i<6;i++){wifi_mac[i]=i?0:2;wifi_ais_connection.selected.ap[i]=i?0:2;}
    wifi_mac[5]=1;wifi_ais_connection.selected.ap[5]=2;
}
int eapol(unsigned port,unsigned tc,const uint8_t *p,unsigned n){return sdio_wifi_wpa_eapol_submit(port,tc,p,n);}
unsigned state(unsigned i){unsigned s[]={wifi_tc4_free,wifi_tx_fault,polls,writes,reserved,delays,write_port};return s[i];}
'''
        cls.tmp = tempfile.TemporaryDirectory()
        p = pathlib.Path(cls.tmp.name)
        (p / 'tc4.c').write_text(harness + body + wrappers)
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(p / 'tc4.c'), '-o', str(p / 'tc4.so')], check=True)
        cls.c = ctypes.CDLL(str(p / 'tc4.so'))
        cls.c.submit.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        cls.c.eapol.argtypes = [ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint]
        cls.c.reset.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
                               ctypes.c_int, ctypes.c_uint, ctypes.c_uint32]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def state(self):
        return [self.c.state(i) for i in range(7)]

    def test_security_header_preserved_and_credit_reserved_before_fifo(self):
        # HIF16 + Ethernet18, padded to 36, AIS0 1X flag and TC4.
        packet = bytes([34, 0, 14, 16, 14, 64, 0, 0, 0, 0, 0, 32]) + bytes(24)
        buffer = ctypes.create_string_buffer(packet)
        self.c.reset(1, 4, 0, 0, 0, 0)
        self.assertEqual(self.c.wait_credit(), 0)
        self.assertEqual(self.c.submit(buffer, 36), 0)
        self.assertEqual(buffer.raw[:36], packet)
        self.assertEqual(self.state(), [3, 0, 1, 1, 3, 0, 0x2c])

    def test_uncertain_write_is_not_refunded_or_retried(self):
        packet = b'\x08\0' + bytes(6)
        self.c.reset(1, 4, 0, -1, 0, 0)
        self.assertEqual(self.c.submit(packet, 8), -1)
        self.assertEqual(self.state(), [3, 1, 0, 1, 3, 0, 0x2c])
        self.assertEqual(self.c.wait_credit(), -1)
        self.assertEqual(self.c.submit(packet, 8), -1)
        self.assertEqual(self.state(), [3, 1, 0, 1, 3, 0, 0x2c])

    def test_empty_pool_polls_until_release(self):
        self.c.reset(1, 0, 0, 0, 3, 0)
        self.assertEqual(self.c.wait_credit(), 0)
        self.assertEqual(self.state(), [1, 0, 3, 0, 0, 2, 0])

    def test_unresolved_connection_blocks_raw_hif_without_consuming_credit(self):
        self.c.reset(1,4,0,0,0,0)
        self.c.unresolved(1)
        self.assertEqual(self.c.submit(b'\x08\0'+bytes(6),8),-1)
        self.assertEqual(self.state(),[4,0,0,0,0,0,0])

    def test_timeout_wrap_and_poll_failure_never_write(self):
        self.c.reset(1, 0, 0, 0, 0, 0xfffffff0)
        self.assertEqual(self.c.wait_credit(), -1)
        self.assertEqual(self.state(), [0, 0, 1001, 0, 0, 1000, 0])
        self.c.reset(1, 4, -1, 0, 0, 0)
        self.assertEqual(self.c.wait_credit(), -1)
        self.assertEqual(self.state(), [4, 0, 1, 0, 0, 0, 0])

    def test_invalid_credit_balance_and_unready_radio(self):
        for ready, credits in [(0, 4), (1, 0), (1, 5)]:
            self.c.reset(ready, credits, 0, 0, 0, 0)
            self.assertEqual(self.c.submit(b'\x08\0' + bytes(6), 8), -1)
            self.assertEqual(self.c.state(3), 0)
        self.c.reset(1, 5, 0, 0, 0, 0)
        self.assertEqual(self.c.wait_credit(), -1)
        self.assertEqual(self.c.state(1), 1)

    def test_invalid_lengths_do_not_consume_credits(self):
        for n, logical in [(0, 0), (7, 7), (9, 9), (516, 516), (4608, 4608),
                           (8, 7), (8, 9)]:
            packet = logical.to_bytes(2, 'little') + bytes(max(n - 2, 6))
            self.c.reset(1, 4, 0, 0, 0, 0)
            self.assertEqual(self.c.submit(packet, n), -1)
            self.assertEqual(self.state(), [4, 0, 0, 0, 0, 0, 0])
        self.c.reset(1, 4, 0, 0, 0, 0)
        self.assertEqual(self.c.submit(None, 8), -1)
        self.assertEqual(self.c.submit(b'\x10\0' + bytes(1022), 1024), 0)

    def security_packet(self):
        p=bytearray(36);p[:6]=bytes([34,0,14,16,14,64]);p[11]=32
        p[16:22]=bytes.fromhex('020000000002');p[22:28]=bytes.fromhex('020000000001')
        p[28:34]=bytes.fromhex('888e02030000');return p

    def test_actual_eapol_gate_reserves_one_credit_and_never_refunds_uncertain_write(self):
        for result in (0,-1):
            self.c.reset(1,4,0,result,0,0);self.c.wpa_ready(0)
            p=bytes(self.security_packet())
            self.assertEqual(self.c.eapol(0x2c,4,p,len(p)),result)
            self.assertEqual(self.state(),[3,int(result!=0),1,1,3,0,0x2c])

    def test_eapol_requires_selected_activated_peer_and_ready_radio(self):
        p=bytes(self.security_packet())
        for missing in [1,2,4,8,16,32,64]:
            self.c.reset(1,4,0,0,0,0);self.c.wpa_ready(missing)
            self.assertEqual(self.c.eapol(0x2c,4,p,len(p)),-1)
            self.assertEqual(self.state(),[4,0,0,0,0,0,0])
        self.c.reset(1,4,0,0,0,0);self.c.wpa_ready(0);self.c.unresolved(1)
        self.assertEqual(self.c.eapol(0x2c,4,p,len(p)),-1)
        self.assertEqual(self.state(),[4,0,0,0,0,0,0])

    def test_eapol_rejects_foreign_peer_hif_payload_and_padding_without_io(self):
        base=self.security_packet()
        for offset in range(len(base)):
            p=base.copy();p[offset]^=0x80
            self.c.reset(1,4,0,0,0,0);self.c.wpa_ready(0)
            self.assertEqual(self.c.eapol(0x2c,4,bytes(p),len(p)),-1,offset)
            self.assertEqual(self.state(),[4,0,0,0,0,0,0])
        for port,tc in ((0x30,4),(0x2c,1)):
            self.c.reset(1,4,0,0,0,0);self.c.wpa_ready(0)
            self.assertEqual(self.c.eapol(port,tc,bytes(base),len(base)),-1)
            self.assertEqual(self.state(),[4,0,0,0,0,0,0])


if __name__ == '__main__':
    unittest.main()
