"""Exercise the real downloader when HIF still reports WLAN_READY."""
import ctypes
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BootReload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'src/sdio.c').read_text()
        start = source.index('static int radio_boot(unsigned force){')
        body = source[start:source.index('\nvoid sdio_wifi_boot(void)', start)]
        harness = r'''
#include <stdint.h>
#include <string.h>
typedef uint32_t TickType_t;
static const uint8_t wifi_radio_bytes[0x21580]={0};
static unsigned card_verified,mode,downloads,total,pll,done,ready,failed,bad,identified;
static unsigned wifi_scan_unresolved;
static unsigned wifi_connection_unresolved;
static uint16_t clock_reg;
static uint32_t ticks;
#define S(a) clock_reg
static int radio_image_valid(void){return mode!=3;}
static void sdio_identify(void){identified++;card_verified=1;}
static int direct(unsigned f,unsigned a,uint8_t *v,unsigned w){
 (void)f;(void)v;return a==2 && w==1?0:-1;
}
static int read_byte(unsigned a,uint8_t *v){if(a!=3)return -1;*v=2;return 0;}
static TickType_t xTaskGetTickCount(void){return ticks;}
static void vTaskDelay(unsigned n){ticks+=n;}
static int radio_read(unsigned a,uint32_t *v){
 if(a==0){*v=0x205931;return 0;} /* stale WLAN_READY throughout */
 if(a==0x8c){*v=0x800;return 0;}
 if(a==4){*v=0x100;return 0;}
 return -1;
}
static int radio_write(unsigned a,uint32_t v){
 if(a==0x90 && v==(0x21580>>6))return 0;
 if(a==0x8c && v==1)return 0;
 if(a==0x88 && v<=1)return 0;
 if(a==0x84 && v==0xff900000)return 0;
 if(a==4 && v==0x200)return 0;
 bad++;return -1;
}
static int radio_wait(unsigned a,uint32_t mask,uint32_t reject){
 (void)reject;
 if(a==0x8c && mask==0x2000){pll++;return mode==1?-1:0;}
 if(a==0x8c && mask==0x8000){done++;return mode==2?-1:0;}
 if(a==0x8c && mask==0x800)return 0;
 if(a==0x88 && mask==0x100)return 0;
 if(a==0 && mask==0x200000)return 0;
 if(a==4 && mask==0x100)return 0;
 bad++;return -1;
}
static int extended_write(unsigned a,const uint8_t *p,unsigned n,int increment){
 if(a!=0x80 || increment || n>512 || n<8 || (n&3) ||
    (p[0]|((unsigned)p[1]<<8))!=n || p[2] || p[3]){bad++;return -1;}
 unsigned remaining=0x21580-total,amount=remaining>508?508:remaining;
 if(n!=((amount+7)&~3U)){bad++;return -1;}
 for(unsigned i=4;i<n;i++)if(p[i]){bad++;return -1;}
 total+=amount;downloads++;return 0;
}
static void field(const char *s,uint32_t n){(void)s;(void)n;}
static void uart_puts(const char *s){
 if(!strcmp(s,"WIFI boot end status=ready\n"))ready++;
 if(strstr(s,"WIFI boot end status=failed\n"))failed++;
}
void reset(unsigned m){mode=m;card_verified=1;clock_reg=0x100;ticks=0;
 wifi_scan_unresolved=1;
 wifi_connection_unresolved=1;
 downloads=total=pll=done=ready=failed=bad=identified=0;}
unsigned state(unsigned i){unsigned v[]={downloads,total,pll,done,ready,failed,bad,identified};return v[i];}
unsigned unresolved(void){return wifi_scan_unresolved;}
unsigned connection_unresolved(void){return wifi_connection_unresolved;}
'''
        cls.tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(cls.tmp.name)
        (path / 'boot.c').write_text(harness + body + '\nint boot(unsigned force){return radio_boot(force);}\n')
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(path / 'boot.c'), '-o', str(path / 'boot.so')], check=True)
        cls.c = ctypes.CDLL(str(path / 'boot.so'))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def state(self):
        return [self.c.state(i) for i in range(8)]

    def test_normal_boot_can_retain_ready_firmware(self):
        self.c.reset(0)
        self.assertEqual(self.c.boot(0), 0)
        self.assertEqual(self.state(), [0, 0, 0, 0, 1, 0, 0, 1])
        self.assertEqual(self.c.unresolved(), 1)
        self.assertEqual(self.c.connection_unresolved(),1)

    def test_forced_reload_downloads_every_byte_despite_stale_ready(self):
        self.c.reset(0)
        self.assertEqual(self.c.boot(1), 0)
        self.assertEqual(self.state(), [269, 0x21580, 1, 1, 1, 0, 0, 0])
        self.assertEqual(self.c.unresolved(), 0)
        self.assertEqual(self.c.connection_unresolved(),0)

    def test_download_failure_cannot_be_hidden_by_stale_ready(self):
        for mode in (1, 2):
            self.c.reset(mode)
            self.assertEqual(self.c.boot(1), -1)
            self.assertEqual(self.state()[4:7], [0, 1, 0])
            self.assertEqual(self.c.unresolved(), 1)
            self.assertEqual(self.c.connection_unresolved(),1)

    def test_bad_blob_prevents_host_initialization(self):
        self.c.reset(3)
        self.assertEqual(self.c.boot(1), -1)
        self.assertEqual(self.state(), [0, 0, 0, 0, 0, 1, 0, 0])


if __name__ == '__main__':
    unittest.main()
