"""Status LED wiring and patterns against a simulated SH726A port register block."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
BOARD_H='''#include <stdint.h>
extern uint8_t sim[0x100];
#define R8(a) (*(volatile uint8_t *)(sim+((a)-0xfffe3800UL)))
'''
STUB='''#include "board.h"
uint8_t sim[0x100];
'''
class Led(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'board.h').write_text(BOARD_H);(p/'stub.c').write_text(STUB)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'include'),
            str(ROOT/'src/board_led.c'),str(p/'stub.c'),'-o',str(p/'led.so')],check=True)
        cls.lib=p/'led.so';cls.n=0
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def load(self):
        Led.n+=1;path=pathlib.Path(self.tmp.name)/f'led{Led.n}.so';path.write_bytes(self.lib.read_bytes())
        c=ctypes.CDLL(str(path));self.sim=(ctypes.c_uint8*0x100).in_dll(c,'sim')
        c.board_led_init.restype=ctypes.c_int;c.board_led_set.argtypes=[ctypes.c_uint,ctypes.c_uint]
        c.board_led_state.argtypes=[ctypes.c_uint];c.board_led_service.argtypes=[ctypes.c_uint,ctypes.c_int]
        return c
    def reg8(self,address):return self.sim[address-0xfffe3800]
    def set_strap(self,strap):
        # PBDR0 (0xfffe3836) bits 9..7; big endian 16-bit register
        value=(strap&7)<<7;self.sim[0x36]=value>>8;self.sim[0x37]=value&0xff   # big endian, as on the SH
    def test_strap2_is_pe0_pe1_with_pfc_ior_and_dr_as_stock(self):
        c=self.load();self.set_strap(2)
        self.sim[0x8f]=0xff
        self.assertEqual(c.board_led_init(),2)
        self.assertEqual(self.reg8(0xfffe388f),0xcc)               # PFC: bits 5,4,1,0 cleared
        self.assertEqual(self.reg8(0xfffe3893)&3,3)                # outputs
        self.assertEqual(self.reg8(0xfffe3897)&3,3)                # idle high = dark
    def test_strap2_leds_are_active_low_on_pe0_and_pe1(self):
        c=self.load();self.set_strap(2);c.board_led_init()
        c.board_led_set(0,1);self.assertEqual(self.reg8(0xfffe3897)&3,2)
        c.board_led_set(1,1);self.assertEqual(self.reg8(0xfffe3897)&3,0)
        c.board_led_set(0,0);self.assertEqual(self.reg8(0xfffe3897)&3,1)
    def test_other_straps_use_pb12_13_and_pc3_4(self):
        c=self.load();self.set_strap(1);self.assertEqual(c.board_led_init(),1)
        self.assertEqual(self.reg8(0xfffe3832)&0x30,0x30);self.assertEqual(self.reg8(0xfffe3836)&0x30,0x30)
        c.board_led_set(1,1);self.assertEqual(self.reg8(0xfffe3836)&0x30,0x10)
        c=self.load();self.set_strap(0);self.assertEqual(c.board_led_init(),0)
        self.assertEqual(self.reg8(0xfffe3853)&0x18,0x18);c.board_led_set(0,1);self.assertEqual(self.reg8(0xfffe3857)&0x18,0x10)
    def test_unknown_strap_touches_nothing(self):
        c=self.load();self.set_strap(4);before=bytes(self.sim)
        self.assertEqual(c.board_led_init(),-1);self.assertEqual(bytes(self.sim),before)
    def test_rf_switch_bits_pb14_pb15_are_never_modified(self):
        for strap in (0,1,2):
            c=self.load();self.set_strap(strap);self.sim[0x36]|=0xc0;before=self.sim[0x36]&0xc0   # PB15,PB14 = bits 7,6 of the first byte
            c.board_led_init();c.board_led_set(0,1);c.board_led_set(1,1)
            self.assertEqual(self.sim[0x36]&0xc0,before)
    def test_state_patterns(self):
        c=self.load();self.set_strap(2);c.board_led_init()
        def lit(now,streaming=0):
            c.board_led_service(now,streaming);v=self.reg8(0xfffe3897)&3;return (not v&1,not v&2)
        c.board_led_state(1);self.assertEqual(lit(0),(False,True))                 # busy: LED1 solid
        c.board_led_state(2);self.assertEqual(lit(0),(True,False))                 # ready: LED0 solid
        self.assertEqual(lit(0,1),(True,False));self.assertEqual(lit(300,1),(True,True))  # streaming: LED1 blinks
        c.board_led_state(3);self.assertEqual(lit(0),(False,False));self.assertEqual(lit(150),(True,True))
        c.board_led_state(0);self.assertEqual(lit(0),(False,False))
    def test_manual_control_pauses_the_pattern_until_auto(self):
        c=self.load();self.set_strap(2);c.board_led_init();c.board_led_state(2)
        c.board_led_set(1,1);c.board_led_service(0,0);self.assertEqual(self.reg8(0xfffe3897)&3,1+0)  # LED0 stays dark: manual
        c.board_led_auto();c.board_led_service(0,0);self.assertEqual(self.reg8(0xfffe3897)&3,2)
if __name__=='__main__':unittest.main()
