"""Fixed-rate serialization and actual station command negotiation guards."""
import ctypes as C,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Fixed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        source=(ROOT/'src/sdio.c').read_text(encoding='utf-8');a=source.index('static int station_update(');b=source.index('/* Limit TS outstanding',a)
        harness=r'''#include <stdint.h>
#include <string.h>
#include "wifi_rates.h"
#include "wifi_station.h"
#include "wifi_ht.h"
#include "wifi_fixed_rate.h"
static unsigned wifi_rate_profile,wifi_fixed54,wifi_fixed_mcs,wifi_ht_enabled,calls;
static uint8_t wifi_peer[6]={2,0,0,0,0,1},saved[48],wifi_peer_rcpi=123;
static uint16_t wifi_peer_rates=0x3fcf,wifi_peer_listen=3;
static struct wifi_ht_peer wifi_peer_ht;
static int control_set(unsigned c,uint8_t *p,unsigned n){if(c!=0x17 || n!=48)return -1;memcpy(saved,p,n);calls++;return 0;}
static void field(const char *s,unsigned v){(void)s;(void)v;}
static void uart_puts(const char *s){(void)s;}
'''
        wrapper=r'''
int station(unsigned legacy,unsigned mcs,unsigned ht,unsigned peer_mcs){
 wifi_fixed54=legacy;wifi_fixed_mcs=mcs;wifi_ht_enabled=ht;calls=0;memset(saved,90,48);
 wifi_peer_ht=(struct wifi_ht_peer){.present=ht,.qos=ht,.mcs=peer_mcs,.capability=0x6e,.ampdu=3};
 return station_update(3,1);
}
const uint8_t *result(void){return saved;}
unsigned count(void){return calls;}
'''
        (p/'station.c').write_text(harness+source[a:b]+wrapper,encoding='utf-8')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(p/'station.c'),str(ROOT/'src/wifi_station.c'),str(ROOT/'src/wifi_rates.c'),str(ROOT/'src/wifi_ht.c'),str(ROOT/'src/wifi_fixed_rate.c'),'-o',str(p/'fixed.so')],check=True)
        cls.c=C.CDLL(str(p/'fixed.so'));cls.c.result.restype=C.c_void_p
        cls.c.wifi_fixed_rate_apply.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_void_p]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def command(self,legacy,mcs,ht=1,peer=255):
        self.assertEqual(self.c.station(legacy,mcs,ht,peer),0);self.assertEqual(self.c.count(),1)
        return C.string_at(self.c.result(),48)
    def test_actual_legacy_override_clears_ht_after_negotiated_fields(self):
        for mode in [1,2]:
            b=self.command(mode,0);self.assertEqual(b[21:26],bytes([2,0,32,0,32]))
            self.assertEqual(b[29:31],bytes(2));self.assertEqual(b[32:34],bytes(2));self.assertEqual(b[41:43],bytes([123,1]))
        b=self.command(0,0);self.assertEqual(b[21],19);self.assertEqual(b[29],255)
    def test_actual_fixed_mcs_uses_index_and_ht_selector(self):
        for mode,index in [(1,0),(2,7)]:
            b=self.command(0,mode);self.assertEqual(b[21:26],bytes([16,0,64,0,64]));self.assertEqual(b[29:31],bytes([index,0]))
            self.assertEqual(b[32]&0x72,0);self.assertEqual(b[26:29],bytes([1,0,2]));self.assertEqual(b[41:43],bytes([123,1]))
    def test_unnegotiated_or_conflicting_fixed_rate_is_not_sent(self):
        for legacy,mcs,ht,peer in [(1,1,1,255),(0,2,1,1),(0,1,1,128),(0,1,0,255),(0,3,1,255)]:
            self.assertEqual(self.c.station(legacy,mcs,ht,peer),-1);self.assertEqual(self.c.count(),0);self.assertEqual(C.string_at(self.c.result(),48),bytes([90])*48)
    def test_invalid_apply_preserves_command(self):
        for length,legacy,mcs in [(47,0,0),(49,0,0),(48,3,0),(48,0,3),(48,1,1),(48,0,1)]:
            b=C.create_string_buffer(bytes([90])*48,48);self.assertEqual(self.c.wifi_fixed_rate_apply(b,length,legacy,mcs,None),0);self.assertEqual(b.raw,bytes([90])*48)
if __name__=='__main__':unittest.main()
