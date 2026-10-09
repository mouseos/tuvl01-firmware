"""Bounded firmware PS/absence observations, with no fabricated known state."""
import ctypes,pathlib,struct,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
NAMES='bss_events ps_events quota_events foreign invalid known absent in_ps bss_quota ps_mode ps_quota quota_mode quota'.split()
class State(ctypes.Structure):
    _fields_=[(name,ctypes.c_uint32) for name in NAMES]
class Power(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();library=pathlib.Path(cls.tmp.name)/'power.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(ROOT/'src/wifi_power_events.c'),'-o',str(library)],check=True)
        cls.c=ctypes.CDLL(str(library))
        cls.c.wifi_power_events_observe.argtypes=[ctypes.POINTER(State),ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint]
        cls.c.wifi_power_events_reset.argtypes=[ctypes.POINTER(State)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def packet(self,eid,body):return struct.pack('<HHBBBB',12,1,eid,91,0,0)+bytes(body)
    def observe(self,state,p):return self.c.wifi_power_events_observe(ctypes.byref(state),p,len(p),1,0)
    def test_unknown_until_event_and_reset_removes_prior_peer_state(self):
        s=State();self.assertEqual(s.known,0)
        self.assertEqual(self.observe(s,self.packet(0x1a,[0,1,2,7])),1)
        self.assertEqual((s.known,s.in_ps,s.ps_mode,s.ps_quota),(2,1,2,7))
        self.c.wifi_power_events_reset(ctypes.byref(s));self.assertEqual(bytes(s),bytes(ctypes.sizeof(s)))
        self.c.wifi_power_events_reset(None)
    def test_absence_ps_and_quota_independent_raw_modes_not_accumulated(self):
        s=State()
        for p in (self.packet(0x19,[1,1,17,0]),self.packet(0x1a,[0,0,3,9]),self.packet(0x1e,[0,2,4,0])):
            self.assertEqual(self.observe(s,p),1)
        self.assertEqual((s.known,s.bss_events,s.ps_events,s.quota_events),(7,1,1,1))
        self.assertEqual((s.absent,s.bss_quota,s.in_ps,s.ps_mode,s.ps_quota,s.quota_mode,s.quota),(1,17,0,3,9,2,4))
        self.observe(s,self.packet(0x1e,[0,2,4,0]));self.assertEqual((s.quota_events,s.quota),(2,4))
    def test_foreign_targets_and_unrelated_events_do_not_change_target(self):
        s=State()
        for p in (self.packet(0x19,[0,1,5,0]),self.packet(0x1a,[1,1,0,5]),self.packet(0x1e,[1,0,5,0])):
            self.assertEqual(self.observe(s,p),2)
        self.assertEqual((s.foreign,s.known,s.ps_events,s.quota_events,s.bss_events),(3,0,0,0,0))
        before=bytes(s);self.assertEqual(self.observe(s,self.packet(0x17,[0,1,0,0])),0);self.assertEqual(bytes(s),before)
    def test_unknown_boolean_clears_only_relevant_known_bit_and_preserves_raw(self):
        s=State();self.observe(s,self.packet(0x19,[1,0,5,0]));self.observe(s,self.packet(0x1a,[0,0,0,5]))
        self.observe(s,self.packet(0x1a,[0,255,255,255]));self.assertEqual((s.known,s.in_ps,s.ps_mode,s.ps_quota),(1,255,255,255))
        self.observe(s,self.packet(0x19,[1,2,255,0]));self.assertEqual((s.known,s.absent),(0,2))
    def test_bad_layout_never_updates_state_other_than_invalid_count(self):
        valid=self.packet(0x1a,[0,1,0,7]);cases=[valid[:n] for n in range(12)]+[valid+b'\0']
        for offset in (0,1,2,3):
            p=bytearray(valid);p[offset]^=2;cases.append(bytes(p))
        for p in cases:
            s=State();self.assertEqual(self.observe(s,p),-1)
            self.assertEqual(s.invalid,1);s.invalid=0;self.assertEqual(bytes(s),bytes(ctypes.sizeof(s)))
        s=State();self.assertEqual(self.c.wifi_power_events_observe(ctypes.byref(s),None,12,1,0),-1)
        self.assertEqual(self.c.wifi_power_events_observe(None,valid,12,1,0),-1)
    def test_event_hook_and_reset_are_in_actual_ap_path_without_tx_credit_mutation(self):
        src=(ROOT/'src/sdio.c').read_text()
        begin=src.index('    /* Power observations never grant HIF credits')
        end=src.index('    if(packet[4]==0x18',begin)
        hook=src[begin:end]
        harness='''
#include <stdint.h>
#include "wifi_power_events.h"
static struct wifi_power_events wifi_power;
static unsigned wifi_verbose,lines;
static void field(const char *name,unsigned value){(void)name;(void)value;}
static void uart_puts(const char *text){(void)text;++lines;}
void verbose(unsigned enabled){wifi_verbose=enabled;}
unsigned logged(void){return lines;}
void event(unsigned wifi_ap_active,const uint8_t *packet,unsigned stated){
unsigned type=packet[2]|((unsigned)packet[3]<<8);
'''+hook+'}\nuint32_t events(void){return wifi_power.ps_events;}\n'
        p=pathlib.Path(self.tmp.name);(p/'hook.c').write_text(harness)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
            str(p/'hook.c'),str(ROOT/'src/wifi_power_events.c'),'-o',str(p/'hook.so')],check=True)
        c=ctypes.CDLL(str(p/'hook.so'));c.event.argtypes=[ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint]
        packet=self.packet(0x1a,[0,1,0,7]);c.event(0,packet,12);self.assertEqual(c.events(),0)
        self.assertEqual(c.logged(),1)
        c.event(1,packet,12);self.assertEqual(c.events(),1);self.assertEqual(c.logged(),1)
        c.verbose(1);c.event(1,packet,12)
        self.assertEqual(c.events(),2);self.assertEqual(c.logged(),2)
        c.verbose(0);c.event(1,self.packet(0x1a,[1,1,0,7]),12)
        self.assertEqual(c.events(),2);self.assertEqual(c.logged(),3)
        c.event(1,packet,11);self.assertEqual(c.events(),2);self.assertEqual(c.logged(),4)
        c.event(1,self.packet(0x17,[0,0,0,0]),12);self.assertEqual(c.logged(),5)
        ap=src[src.index('void sdio_wifi_ap(void){'):src.index('void sdio_wifi_rate(void){')]
        self.assertIn('wifi_power_events_reset(&wifi_power);',ap)
        self.assertNotIn('wifi_tc',hook)
if __name__=='__main__':unittest.main()
