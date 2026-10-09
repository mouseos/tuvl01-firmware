import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Watch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        headers={'board.h':'#include <stdint.h>\nvoid uart_puts(const char*);void uart_hex(unsigned);',
                 'FreeRTOS.h':'typedef uint32_t TickType_t;\n#define pdMS_TO_TICKS(x) (x)',
                 'task.h':'TickType_t xTaskGetTickCount(void);',
                 'tuner.h':'int tuner_read_register(unsigned,unsigned,uint8_t*);',
                 'tuner_ts.h':'int tuner_ts_stream_active(void);unsigned tuner_ts_stream_packet_count(void);'}
        for name,s in headers.items():(p/name).write_text(s)
        (p/'mock.c').write_text(r"""
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint8_t regs[256];static uint32_t tick;static unsigned reads,fail,tx,active;static char logs[24000];
void uart_puts(const char*s){unsigned n=0;while(logs[n])n++;while(*s && n+1<sizeof logs)logs[n++]=*s++;logs[n]=0;}
void uart_hex(unsigned n){char b[9];snprintf(b,sizeof b,"%08x",n);uart_puts(b);}
uint32_t xTaskGetTickCount(void){return tick;}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t*v){(void)bank;reads++;tick+=2;if(reads==fail)return -1;*v=regs[reg];return 0;}
int tuner_ts_stream_active(void){return active;}
unsigned tuner_ts_stream_packet_count(void){return tx;}
void setup(unsigned error,uint32_t now){for(unsigned i=0;i<256;i++)regs[i]=i;tick=now;reads=tx=0;fail=error;active=1;logs[0]=0;}
void advance(unsigned ms){tick+=ms;tx+=32;}
void mutate(unsigned r){regs[r]^=1;}
unsigned accesses(void){return reads;}
const char* output(void){return logs;}
void clear_output(void){logs[0]=0;}
""")
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'include'),str(ROOT/'src/tuner_quality_watch.c'),str(p/'mock.c'),'-o',str(p/'watch.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'watch.so'));cls.c.output.restype=ctypes.c_char_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setup(self,error=0,tick=0):
        self.c.tuner_quality_watch_dump();self.c.setup(error,tick);self.c.tuner_quality_watch_start();self.c.clear_output()
    def poll(self,n):
        for _ in range(n):
            before=self.c.accesses();self.c.advance(1);self.c.tuner_quality_watch_poll()
            self.assertLessEqual(self.c.accesses()-before,1)
    def log(self):self.c.tuner_quality_watch_dump();return self.c.output().decode()
    def test_finite_interval_no_uart_during_sampling_and_tx_continues(self):
        self.setup();self.poll(30);self.assertEqual(self.c.output(),b'')
        reads=self.c.accesses();self.poll(100);self.assertEqual(self.c.accesses(),reads)
        for _ in range(15):self.c.advance(1000);self.poll(30)
        self.poll(1000);self.assertEqual(self.c.accesses(),480)
        s=self.log();self.assertIn('count=00000010',s);self.assertEqual(s.count('QUALITY watch sample='),16)
        self.assertIn('active=00000003',s);self.assertIn('failed_read=00000000',s)
        self.assertIn('io_ticks=0000003c',s)
    def test_tick_wrap_and_total_deadline(self):
        self.setup(tick=0xfffffff0);self.poll(30);self.c.advance(30000);self.poll(10)
        self.assertEqual(self.c.accesses(),30);self.assertIn('count=00000001',self.log())
    def test_read_failure_is_recorded_and_does_not_loop(self):
        self.setup(error=6);self.poll(30);self.assertEqual(self.c.accesses(),6)
        self.assertIn('failed_read=00000006',self.log())
    def test_changed_raw_value_and_partial_cancel_are_preserved(self):
        self.setup();self.poll(20);self.c.mutate(0xc4);self.poll(10)
        self.assertIn('changed=00008000',self.log())
        self.setup();self.poll(4);s=self.log();self.assertIn('partial_reads=00000004',s)
        self.poll(100);self.assertEqual(self.c.accesses(),4)
if __name__=='__main__':unittest.main()
