import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Quality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        headers={
            'board.h':'#include <stdint.h>\nvoid uart_puts(const char*);void uart_hex(unsigned);',
            'tuner.h':'int tuner_read_register(unsigned,unsigned,uint8_t*);int tuner_write_register(unsigned,unsigned,uint8_t);',
            'tuner_monitor.h':'int tuner_frame_state(uint8_t,uint8_t);void tuner_quality(void);',
            'FreeRTOS.h':'typedef unsigned TickType_t;\n#define pdMS_TO_TICKS(x) (x)',
            'task.h':'TickType_t xTaskGetTickCount(void);void vTaskDelay(TickType_t);'}
        for name,text in headers.items():(p/name).write_text(text)
        (p/'mock.c').write_text('''#include <stdint.h>
#include <string.h>
static uint8_t regs[3][256],original[3][256];static unsigned tick,writes,fail;static char logbuf[4096];
void uart_puts(const char*s){strncat(logbuf,s,sizeof logbuf-strlen(logbuf)-1);}void uart_hex(unsigned v){(void)v;}
int tuner_frame_state(uint8_t a,uint8_t b){(void)a;(void)b;return 0;}
unsigned xTaskGetTickCount(void){return tick++;}void vTaskDelay(unsigned n){tick+=n;}
int tuner_read_register(unsigned bank,unsigned r,uint8_t*v){*v=regs[bank-0x60][r];return 0;}
int tuner_write_register(unsigned bank,unsigned r,uint8_t v){if(++writes==fail)return -1;regs[bank-0x60][r]=v;return 0;}
void setup(unsigned nth,unsigned ready,unsigned denominator){memset(regs,0,sizeof regs);memset(logbuf,0,sizeof logbuf);tick=writes=0;fail=nth;
regs[1][0x97]=0x74;regs[1][0xbf]=3;regs[1][0xc3]=ready;regs[1][0xc8]=denominator;
regs[1][0x8b]=0x59;regs[1][0x90]=4;regs[1][0x91]=0x39;regs[1][0x93]=4;memcpy(original,regs,sizeof regs);}
int restored(void){return !memcmp(original,regs,sizeof regs);}const char* output(void){return logbuf;}
''')
        lib=p/'quality.so';subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(p),str(ROOT/'src/tuner_monitor.c'),str(p/'mock.c'),'-o',str(lib)],check=True)
        cls.lib=ctypes.CDLL(str(lib));cls.lib.output.restype=ctypes.c_char_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_measurement(self,nth=0,ready=0xff,denominator=0):
        self.lib.setup(nth,ready,denominator);self.lib.tuner_quality()
        self.assertEqual(self.lib.restored(),1)
        return self.lib.output().decode()
    def test_zero_denominator_is_not_zero_error_rate(self):
        s=self.run_measurement();self.assertIn('status=zero-denominator',s);self.assertNotIn('status=counts-raw',s)
    def test_each_partial_write_failure_restores_controls(self):
        for nth in range(1,7):
            with self.subTest(nth=nth):
                s=self.run_measurement(nth);self.assertIn('controls status=restored',s);self.assertIn('end status=i2c-failed',s)
    def test_not_ready_is_bounded_and_controls_restored(self):
        self.assertIn('end status=counter-not-ready',self.run_measurement(ready=0))
    def test_nonzero_denominator_is_only_raw_counts(self):
        self.assertIn('end status=counts-raw',self.run_measurement(denominator=100))
