"""Exercise actual tuning writes, including unrelated trigger bits and failures."""
import ctypes,json,pathlib,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from tune import encode

class Trigger(unittest.TestCase):
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
static uint8_t input[32],regs[3][256];static unsigned pos,tick,reads,writes,readfail,writefail;static char output[4096];
void uart_puts(const char*s){unsigned at=strlen(output),n=strlen(s);if(n>sizeof output-at-1)n=sizeof output-at-1;memcpy(output+at,s,n);output[at+n]=0;}void uart_hex(unsigned n){(void)n;}
int uart_getc(void){return pos<32?input[pos++]:-1;}
unsigned xTaskGetTickCount(void){return tick++;}void vTaskDelay(unsigned n){tick+=n;}void sdio_wifi_poll(void){}
int sdio_wifi_traffic_active(void){return 0;}int tuner_ts_stream_active(void){return 0;}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t*v){
 if(bank==0x60 && reg==0xba){reads++;if(readfail)return -1;}
 *v=regs[bank-0x60][reg];return 0;
}
int tuner_write_register(unsigned bank,unsigned reg,uint8_t v){
 if(bank==0x60 && reg==0xba){writes++;if(writefail)return -1;}
 regs[bank-0x60][reg]=v;return 0;
}
void setup(const uint8_t*p,unsigned ba,unsigned rf,unsigned wf,unsigned calibrated){
 memcpy(input,p,32);memset(regs,0,sizeof regs);output[0]=0;pos=tick=reads=writes=0;
 readfail=rf;writefail=wf;regs[0][0xba]=ba;regs[0][0xb9]=0x80;regs[0][0xd6]=calibrated;
}
unsigned metric(unsigned n){unsigned values[]={reads,writes,regs[0][0xba]};return values[n];}
const char* log_output(void){return output;}
''')
        lib=p/'trigger.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'include'),str(ROOT/'src/tuner_profile.c'),str(ROOT/'src/tuner_profile_protocol.c'),str(p/'mock.c'),'-o',str(lib)],check=True)
        cls.c=ctypes.CDLL(str(lib));cls.c.log_output.restype=ctypes.c_char_p
        cls.c.setup.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.c_uint,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_tune(self,full=True,ba=0,rf=0,wf=0,calibrated=1,corrupt=False):
        name='uhf-ch14-full.json' if full else 'uhf-ch14-partial.json'
        packet=bytearray(encode(json.loads((ROOT/'profiles'/name).read_text(encoding='utf-8-sig'))))
        if corrupt:packet[-1]^=1
        self.c.setup((ctypes.c_uint8*32).from_buffer_copy(packet),ba,rf,wf,calibrated)
        self.c.tuner_profile_receive()
        return self.c.log_output().decode()
    def test_full_trigger_preserves_every_low_nibble(self):
        for ba in range(256):
            with self.subTest(ba=ba):
                self.assertIn('end status=sequence-complete',self.run_tune(ba=ba))
                self.assertEqual([self.c.metric(i) for i in range(3)],[1,1,ba&15])
    def test_partial_trigger_keeps_existing_whole_byte_write(self):
        self.assertIn('end status=sequence-complete',self.run_tune(full=False,ba=0xab))
        self.assertEqual([self.c.metric(i) for i in range(3)],[0,1,0])
    def test_trigger_read_failure_prevents_trigger_write(self):
        self.assertIn('end status=i2c-failed',self.run_tune(ba=0xab,rf=1))
        self.assertEqual([self.c.metric(i) for i in range(3)],[1,0,0xab])
    def test_trigger_write_failure_is_not_completion(self):
        s=self.run_tune(ba=0xab,wf=1)
        self.assertIn('end status=i2c-failed',s);self.assertNotIn('end status=sequence-complete',s)
        self.assertEqual([self.c.metric(i) for i in range(3)],[1,1,0xab])
    def test_rejected_and_uncalibrated_inputs_do_not_trigger(self):
        for options in ({'corrupt':True},{'calibrated':0}):
            self.run_tune(ba=0xab,**options)
            self.assertEqual([self.c.metric(i) for i in range(3)],[0,0,0xab])
