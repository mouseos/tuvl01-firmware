"""Production CID08 gate with only peripheral command submission replaced."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Keys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text()
        start=source.index('int sdio_wifi_wpa_key_submit(')
        body=source[start:source.index('void sdio_wifi_osc(void){',start)]
        harness=r'''
#include <stdint.h>
#include <string.h>
static unsigned wifi_hif_ready,wifi_mac_valid,wifi_tx_fault,wifi_connection_unresolved;
static unsigned wifi_ap_active,wifi_peer_state,calls,cid,size;
static struct {unsigned watch,activated,beacon_seen,aid;struct {uint8_t ap[6];} selected;} wifi_ais_connection;
static int outcome;static uint8_t captured[72];
static int control_set(unsigned id,uint8_t *p,unsigned n){
    calls++;cid=id;size=n;memcpy(captured,p,n);return outcome;
}
void reset(unsigned missing,int result){
    wifi_hif_ready=!(missing&1);wifi_mac_valid=!(missing&2);wifi_tx_fault=!!(missing&4);
    wifi_connection_unresolved=!!(missing&8);wifi_ap_active=!!(missing&16);wifi_peer_state=!!(missing&32);
    wifi_ais_connection.watch=!(missing&64);wifi_ais_connection.activated=!(missing&128);
    wifi_ais_connection.beacon_seen=!(missing&256);wifi_ais_connection.aid=!(missing&512);
    memset(wifi_ais_connection.selected.ap,0,6);wifi_ais_connection.selected.ap[0]=2;
    wifi_ais_connection.selected.ap[5]=2;calls=cid=size=0;outcome=result;memset(captured,0,72);
}
unsigned state(unsigned i){unsigned s[]={calls,cid,size,wifi_connection_unresolved};return s[i];}
unsigned byte(unsigned i){return captured[i];}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'keys.c').write_text(harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'keys.c'),'-o',str(p/'keys.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'keys.so'));cls.c.sdio_wifi_wpa_key_submit.argtypes=[ctypes.c_void_p,ctypes.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def packet(self,pairwise=True,add=True):
        p=bytearray(64);p[0]=add;p[1]=pairwise and add;p[2]=pairwise
        p[4:10]=bytes.fromhex('020000000002') if pairwise else bytes([255])*6
        p[12]=0 if pairwise else 1
        if add:p[11]=4;p[13]=16;p[16:32]=bytes(range(16))
        return bytes(p)
    def states(self):return [self.c.state(i) for i in range(4)]
    def test_pairwise_group_add_remove_transfer_exact_body(self):
        for pairwise in (False,True):
            for add in (False,True):
                p=self.packet(pairwise,add);self.c.reset(0,0)
                self.assertEqual(self.c.sdio_wifi_wpa_key_submit(p,len(p)),0)
                self.assertEqual(self.states(),[1,8,72,0])
                self.assertEqual(bytes(self.c.byte(i) for i in range(72)),bytes(8)+p)
    def test_uncertain_transfer_latches_unresolved_and_prevents_retry(self):
        p=self.packet();self.c.reset(0,-1)
        self.assertEqual(self.c.sdio_wifi_wpa_key_submit(p,len(p)),-1)
        self.assertEqual(self.states(),[1,8,72,1])
        self.assertEqual(self.c.sdio_wifi_wpa_key_submit(p,len(p)),-1)
        self.assertEqual(self.states(),[1,8,72,1])
    def test_invalid_context_fields_lengths_and_nonzero_rsc_do_not_submit(self):
        base=self.packet()
        for missing in [1<<i for i in range(10)]:
            self.c.reset(missing,0);self.assertEqual(self.c.sdio_wifi_wpa_key_submit(base,64),-1)
            self.assertEqual(self.c.state(0),0)
        for i in list(range(16))+list(range(32,64)):
            p=bytearray(base);p[i]^=128;self.c.reset(0,0)
            self.assertEqual(self.c.sdio_wifi_wpa_key_submit(bytes(p),64),-1,i)
            self.assertEqual(self.c.state(0),0)
        for p,n in ((None,64),(base,63),(base,65)):
            self.c.reset(0,0);self.assertEqual(self.c.sdio_wifi_wpa_key_submit(p,n),-1)
            self.assertEqual(self.c.state(0),0)
