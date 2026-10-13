"""tuner_lock_wait(): bounded wait for stable frame lock that keeps servicing the radio."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Lock(unittest.TestCase):
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
static unsigned tick,reads,lock_after,polls,fail_reads;
void uart_puts(const char*s){(void)s;}void uart_hex(unsigned n){(void)n;}int uart_getc(void){return -1;}
unsigned xTaskGetTickCount(void){return tick;}void vTaskDelay(unsigned n){tick+=n;}void sdio_wifi_poll(void){polls++;}
int sdio_wifi_traffic_active(void){return 0;}int tuner_ts_stream_active(void){return 0;}
int tuner_write_register(unsigned b,unsigned r,uint8_t v){(void)b;(void)r;(void)v;return 0;}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t*v){
  if(bank!=0x61 || reg!=0x97)return -1;
  if(fail_reads)return -1;
  *v=(++reads>lock_after)?0x10:0x00;return 0;
}
void setup(unsigned after,unsigned fail){tick=reads=polls=0;lock_after=after;fail_reads=fail;}
unsigned metric(unsigned n){unsigned m[]={tick,reads,polls};return m[n];}
''')
        lib=p/'lock.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'include'),
            str(ROOT/'src/tuner_profile.c'),str(ROOT/'src/tuner_profile_protocol.c'),str(p/'mock.c'),'-o',str(lib)],check=True)
        cls.c=ctypes.CDLL(str(lib));cls.c.tuner_lock_wait.argtypes=[ctypes.c_uint]
        cls.c.setup.argtypes=[ctypes.c_uint,ctypes.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_already_locked_returns_without_waiting(self):
        self.c.setup(0,0);self.assertEqual(self.c.tuner_lock_wait(4000),1)
        self.assertEqual((self.c.metric(0),self.c.metric(2)),(0,0))
    def test_lock_acquired_after_a_while_services_the_radio_meanwhile(self):
        self.c.setup(5,0);self.assertEqual(self.c.tuner_lock_wait(4000),1)
        self.assertEqual(self.c.metric(1),6);self.assertGreater(self.c.metric(2),0)
        self.assertLess(self.c.metric(0),4000)
    def test_never_locking_times_out_after_the_budget(self):
        self.c.setup(10**9,0);self.assertEqual(self.c.tuner_lock_wait(1000),0)
        self.assertGreaterEqual(self.c.metric(0),1000);self.assertLess(self.c.metric(0),1200)
    def test_register_read_failures_are_not_lock(self):
        self.c.setup(0,1);self.assertEqual(self.c.tuner_lock_wait(500),0)
if __name__=='__main__':unittest.main()
