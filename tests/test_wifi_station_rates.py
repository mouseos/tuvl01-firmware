"""Execute actual station-command and profile-selection bodies."""
import ctypes as C,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Station(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text();start=source.index('void sdio_wifi_rate_profile(void){')
        body=source[start:source.index('/* Limit TS outstanding',start)]
        harness=r'''
#include <stdint.h>
#include <string.h>
#include "wifi_rates.h"
#include "wifi_station.h"
#include "wifi_ht.h"
#include "wifi_fixed_rate.h"
static unsigned wifi_ht_enabled,wifi_fixed_mcs;
static struct wifi_ht_peer wifi_peer_ht;
static unsigned wifi_rate_profile,wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending,wifi_fixed54;
static uint8_t wifi_peer[6]={2,1,2,3,4,5},wifi_peer_rcpi=137,saved[48];
static uint16_t wifi_peer_rates,wifi_peer_listen=3;
static unsigned writes,fail;
static int control_set(unsigned cid,uint8_t *p,unsigned n){
    if(cid!=0x17 || n!=48)return -1;
    memcpy(saved,p,n);writes++;return fail?-1:0;
}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static void uart_puts(const char *s){(void)s;}
void reset(unsigned profile,unsigned mode,unsigned rates){
    wifi_ht_enabled=wifi_fixed_mcs=0;wifi_peer_ht=(struct wifi_ht_peer){0};
    wifi_rate_profile=profile;wifi_fixed54=mode;wifi_peer_rates=rates;
    wifi_ap_active=wifi_peer_state=wifi_peer_activate_pending=fail=writes=0;
    memset(saved,165,sizeof saved);
}
void active(unsigned ap,unsigned peer,unsigned pending){wifi_ap_active=ap;wifi_peer_state=peer;wifi_peer_activate_pending=pending;}
void enable_ht(void){wifi_ht_enabled=1;wifi_peer_ht=(struct wifi_ht_peer){0xffff,0x1b,255,1,1};}
unsigned selected(void){return wifi_rate_profile;}
unsigned submitted(void){return writes;}
const uint8_t *result(void){return saved;}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'station.c').write_text(harness+body+'\nint update(unsigned state,unsigned associated){return station_update(state,associated);}\n')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(p/'station.c'),str(ROOT/'src/wifi_station.c'),str(ROOT/'src/wifi_rates.c'),str(ROOT/'src/wifi_ht.c'),str(ROOT/'src/wifi_fixed_rate.c'),'-o',str(p/'station.so')],check=True)
        cls.c=C.CDLL(str(p/'station.so'));cls.c.result.restype=C.c_void_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_profile_controls_wire_phy_and_basic_rate_with_activation_identity(self):
        for profile,mask,basic,phy in ((0,0x3fcf,0x054f,3),(1,0x3fc0,0x0540,2)):
            self.c.reset(profile,0,mask);self.assertEqual(self.c.update(3,1),0)
            b=C.string_at(self.c.result(),48)
            self.assertEqual(b[8:16],bytes([0,0x22,2,1,2,3,4,5]))
            self.assertEqual(b[16:26],bytes([1,0,3,0,1,phy])+mask.to_bytes(2,'little')+basic.to_bytes(2,'little'))
            self.assertEqual(b[28],3);self.assertEqual(b[41:43],bytes([137,1]))
    def test_fixed54_preserves_literal_verified_word_order_and_refuses_missing_peer_rate(self):
        for profile in (0,1):
            self.c.reset(profile,1,0x3fcf);self.assertEqual(self.c.update(3,1),0)
            b=C.string_at(self.c.result(),48);self.assertEqual(b[21:26],bytes.fromhex('0200200020'))
            self.c.reset(profile,1,0x0540);self.assertEqual(self.c.update(3,1),-1);self.assertEqual(self.c.submitted(),0)
    def test_ht_sets_peer_mcs_and_qos_only_after_association(self):
        self.c.reset(0,0,0x3fcf);self.c.enable_ht();self.assertEqual(self.c.update(1,0),0)
        b=C.string_at(self.c.result(),48);self.assertEqual(b[29:41],bytes(12));self.assertEqual(b[26],0)
        self.assertEqual(self.c.update(3,1),0);b=C.string_at(self.c.result(),48)
        self.assertEqual(b[21],11);self.assertEqual(b[26:28],bytes([1,0]));self.assertEqual(b[29:34],bytes([255,0,27,12,0]))
        self.assertEqual(b[41:43],bytes([137,1]));self.assertEqual(b[8:16],bytes([0,0x22,2,1,2,3,4,5]))
    def test_profile_change_refuses_active_or_retained_peer(self):
        for state in ((1,0,0),(0,1,0),(0,0,1)):
            self.c.reset(0,0,0x3fcf);self.c.active(*state);self.c.sdio_wifi_rate_profile();self.assertEqual(self.c.selected(),0)
        self.c.reset(0,0,0x3fcf);self.c.sdio_wifi_rate_profile();self.assertEqual(self.c.selected(),1)
        self.c.sdio_wifi_rate_profile();self.assertEqual(self.c.selected(),0)
if __name__=='__main__':unittest.main()
