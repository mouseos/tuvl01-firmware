"""Run production control submission with unresolved cleanup and HIF reinit."""
import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ConnectionGuard(unittest.TestCase):
    def test_unresolved_cleanup_prevents_hif_reseed_and_all_hardware_io(self):
        source = (ROOT/'src/sdio.c').read_text()
        start = source.index('static int control_send(unsigned cid,unsigned set,uint8_t *packet,unsigned length){')
        body = source[start:source.index('\nstatic void beacon_read(', start)]
        harness = r'''
#include <stdint.h>
#include <string.h>
static unsigned wifi_connection_unresolved,wifi_hif_ready,wifi_tx_fault;
static unsigned wifi_ais_retained_active,wifi_ais_retained_teardown;
static unsigned wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc4_free,wifi_tc5_free;
static unsigned io;
static uint8_t wifi_sequence;
static uint16_t clock_reg=0x100;
#define S(a) clock_reg
static void uart_puts(const char *s){(void)s;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static int radio_read(unsigned a,uint32_t *v){(void)a;io++;*v=0x205931;return 0;}
static int radio_write(unsigned a,uint32_t v){(void)a;(void)v;io++;return 0;}
static int radio_wait(unsigned a,uint32_t m,uint32_t r){(void)a;(void)m;(void)r;io++;return 0;}
static int read_byte(unsigned a,uint8_t *v){(void)a;io++;*v=2;return 0;}
static int direct(unsigned f,unsigned a,uint8_t *v,int w){(void)f;(void)a;(void)v;(void)w;io++;return 0;}
static int event_read(uint8_t *p,unsigned n,unsigned *used){(void)p;(void)n;io++;*used=0;return 0;}
static int tc4_wait(void){io++;return -1;}
static int tc4_write(const uint8_t *p,unsigned n){(void)p;(void)n;io++;return 0;}
'''
        wrappers = r'''
int run(unsigned ready){
 uint8_t p[12];memset(p,0xa5,sizeof p);
 wifi_connection_unresolved=1;wifi_hif_ready=ready;wifi_tx_fault=1;
 wifi_tc4_free=0;wifi_sequence=77;io=0;
 int result=control_send(0x15,1,p,sizeof p);
 if(result!=-1 || io || wifi_hif_ready!=ready || !wifi_tx_fault || wifi_tc4_free || wifi_sequence!=77)return 0;
 for(unsigned i=0;i<sizeof p;i++)if(p[i]!=0xa5)return 0;
 return 1;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp)
            (p/'guard.c').write_text(harness+body+wrappers)
            subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                            str(p/'guard.c'), '-o', str(p/'guard.so')], check=True)
            lib = C.CDLL(str(p/'guard.so'))
            for ready in (0,1):
                self.assertEqual(lib.run(ready),1)


if __name__ == '__main__':
    unittest.main()
