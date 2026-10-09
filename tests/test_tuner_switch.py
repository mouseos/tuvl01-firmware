"""Run the real mode switch through bus, readback, and recovery failures."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class ModeSwitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        headers={
            'board.h':'#include <stdint.h>\nvoid uart_puts(const char*);void uart_hex(unsigned);int uart_getc(void);',
            'tuner.h':'int tuner_read_register(unsigned,unsigned,uint8_t*);int tuner_write_register(unsigned,unsigned,uint8_t);',
            'sdio.h':'void sdio_wifi_poll(void);int sdio_wifi_traffic_active(void);',
            'tuner_ts.h':'int tuner_ts_stream_active(void);',
            'FreeRTOS.h':'typedef unsigned TickType_t;\n#define pdMS_TO_TICKS(x) (x)',
            'task.h':'TickType_t xTaskGetTickCount(void);void vTaskDelay(TickType_t);'}
        for name,text in headers.items():(p/name).write_text(text)
        (p/'mock.c').write_text('''#include <stdint.h>
#include <string.h>
static uint8_t regs[3][256];static unsigned reads,writes,edwrites,bad,active,ignore,delay;
static uint64_t rf,wf;static char output[4096];
void uart_puts(const char*s){unsigned at=strlen(output),n=strlen(s);if(n>sizeof output-at-1)n=sizeof output-at-1;memcpy(output+at,s,n);output[at+n]=0;}
void uart_hex(unsigned n){(void)n;}int uart_getc(void){return -1;}
unsigned xTaskGetTickCount(void){return 0;}void vTaskDelay(unsigned n){delay+=n;}void sdio_wifi_poll(void){}
int sdio_wifi_traffic_active(void){return active&1;}int tuner_ts_stream_active(void){return active&2;}
int tuner_profile_valid(const uint8_t*p){(void)p;return 0;}
int tuner_read_register(unsigned bank,unsigned r,uint8_t*v){reads++;*v=regs[bank-0x60][r];return (rf>>(reads-1))&1?-1:0;}
int tuner_write_register(unsigned bank,unsigned r,uint8_t v){
 writes++;if(bank!=0x61 || (r!=0xdc && r!=0xdd && r!=0xed))bad++;
 if(r==0xed)edwrites++;
 /* A failed transaction may still have changed the device. */
 if(writes!=ignore)regs[bank-0x60][r]=v;
 return (wf>>(writes-1))&1?-1:0;
}
void setup(unsigned ed,unsigned system,unsigned calibrated,unsigned a,uint64_t readfail,uint64_t writefail,unsigned ignored){
 memset(regs,0,sizeof regs);output[0]=0;reads=writes=edwrites=bad=delay=0;
 active=a;rf=readfail;wf=writefail;ignore=ignored;
 regs[0][0xd6]=calibrated;regs[2][0xf2]=system;regs[1][0xed]=ed;regs[1][0xdc]=0xa5;regs[1][0xdd]=0xd3;
}
unsigned metric(unsigned n){unsigned values[]={reads,writes,edwrites,bad,regs[1][0xed],regs[1][0xdc],regs[1][0xdd],delay};return values[n];}
const char* log_output(void){return output;}
''')
        lib=p/'switch.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'include'),str(ROOT/'src/tuner_profile.c'),str(p/'mock.c'),'-o',str(lib)],check=True)
        cls.c=ctypes.CDLL(str(lib));cls.c.log_output.restype=ctypes.c_char_p
        cls.c.setup.argtypes=[ctypes.c_uint]*4+[ctypes.c_uint64]*2+[ctypes.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_switch(self,ed=0x56,system=4,calibrated=1,active=0,rf=0,wf=0,ignored=0):
        self.c.setup(ed,system,calibrated,active,rf,wf,ignored);self.c.tuner_profile_switch()
        self.assertEqual(self.c.metric(3),0,'RF/PLL or unrelated write')
        return self.c.log_output().decode()
    def assert_masks_restored(self):
        self.assertEqual([self.c.metric(i) for i in (5,6)],[0xa5,0xd3])
    def test_both_directions_verify_mode_and_restore_masks(self):
        for ed in (0x16,0x56):
            self.assertIn('end status=switched',self.run_switch(ed=ed))
            self.assertEqual(self.c.metric(4),ed^0x40);self.assert_masks_restored()
            self.assertEqual(self.c.metric(2),1);self.assertEqual(self.c.metric(7),10)
    def test_active_transfer_refused_without_io(self):
        for active in (1,2,3):
            self.assertIn('end status=refused-active',self.run_switch(active=active))
            self.assertEqual([self.c.metric(i) for i in (0,1)],[0,0])
    def test_only_calibrated_uhf_pair_allowed(self):
        for ed in range(256):
            if ed in (0x16,0x56):continue
            self.assertIn('end status=refused-mode',self.run_switch(ed=ed));self.assertEqual(self.c.metric(1),0)
        for options in ({'system':0x10},{'calibrated':0}):
            self.assertIn('end status=refused-mode',self.run_switch(**options));self.assertEqual(self.c.metric(1),0)
    def test_initial_read_failures_do_not_write(self):
        for nth in range(1,6):
            self.assertIn('end status=i2c-failed',self.run_switch(rf=1<<(nth-1)))
            self.assertEqual(self.c.metric(1),0)
    def test_mask_failures_restore_without_mode_change(self):
        for options in ({'wf':1},{'wf':2},{'rf':1<<5},{'rf':1<<6},{'ignored':1},{'ignored':2}):
            self.assertIn('end status=i2c-failed',self.run_switch(**options));self.assert_masks_restored()
            self.assertEqual(self.c.metric(2),0);self.assertEqual(self.c.metric(4),0x56)
    def test_uncertain_mode_write_and_readback_failure_roll_back(self):
        for options in ({'wf':1<<2},{'rf':1<<7},{'ignored':3}):
            self.assertIn('end status=i2c-failed',self.run_switch(**options));self.assert_masks_restored()
            self.assertEqual(self.c.metric(2),2);self.assertEqual(self.c.metric(4),0x56)
    def test_each_irq_restore_failure_is_reported(self):
        for options in ({'wf':1<<3},{'wf':1<<4},{'rf':1<<8},{'rf':1<<9}):
            self.assertIn('end status=restore-failed',self.run_switch(**options));self.assertEqual(self.c.metric(1),5)
    def test_rollback_failure_is_not_success(self):
        for options in ({'wf':(1<<2)|(1<<3)},{'wf':1<<2,'rf':1<<8}):
            self.assertIn('end status=restore-failed',self.run_switch(**options));self.assert_masks_restored()
