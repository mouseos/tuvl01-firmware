"""Actual CMT sampler: pending IRQ, compare crossing, wrap and nesting."""
import ctypes as C,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Clock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'board.h').write_text('#include <stdint.h>\nunsigned mock_read(unsigned address);\n#define R16(a) mock_read(a)\n',encoding='utf-8')
        (p/'FreeRTOS.h').write_text('#include <stdint.h>\nvoid enter(void),leave(void);\n#define taskENTER_CRITICAL() enter()\n#define taskEXIT_CRITICAL() leave()\n',encoding='utf-8')
        (p/'task.h').write_text('uint32_t xTaskGetTickCount(void);\n',encoding='utf-8')
        (p/'mock.c').write_text(r'''#include <stdint.h>
static uint32_t tick;
static unsigned pre,post,c1,c2,flags,counts,depth,initial,bad;
void setup(uint32_t t,unsigned a,unsigned b,unsigned x,unsigned y,unsigned d){
 tick=t;pre=a;post=b;c1=x;c2=y;flags=counts=bad=0;depth=initial=d;
}
void enter(void){depth++;}
void leave(void){if(depth!=initial+1)bad++;depth--;}
uint32_t xTaskGetTickCount(void){if(depth!=initial+1)bad++;return tick;}
unsigned mock_read(unsigned a){
 if(depth!=initial+1)bad++;
 if(a==0xfffec006)return 4499;
 if(a==0xfffec002)return flags++?post:pre;
 if(a==0xfffec004)return counts++?c2:c1;
 bad++;return 0;
}
unsigned state(unsigned n){unsigned v[]={depth,bad,flags,counts};return v[n];}
''',encoding='utf-8')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'include'),str(ROOT/'src/time_counts.c'),str(p/'mock.c'),'-o',str(p/'clock.so')],check=True)
        cls.c=C.CDLL(str(p/'clock.so'));cls.c.board_time_counts.restype=C.c_uint32
        cls.c.setup.argtypes=[C.c_uint32]*6
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def sample(self,t,a,b,x,y,d=0):
        self.c.setup(t,a,b,x,y,d);v=self.c.board_time_counts()
        self.assertEqual(self.c.state(0),d);self.assertEqual(self.c.state(1),0)
        return v
    def test_subtick_resolution(self):
        self.assertEqual(self.sample(10,0,0,12,0),45012)
        self.assertEqual(self.sample(10,0,0,13,0),45013)
        self.assertEqual(self.c.state(3),1)
    def test_pending_tick_uses_next_epoch(self):
        self.assertEqual(self.sample(10,128,128,17,0),49517)
        self.assertEqual(self.sample(11,0,0,17,0),49517)
    def test_compare_during_read_resamples_new_phase(self):
        before=self.sample(10,0,0,4498,0)
        after=self.sample(10,0,128,4498,5)
        self.assertEqual(after,49505);self.assertEqual(after-before,7)
        self.assertEqual(self.c.state(3),2)
    def test_wrap_and_nested_critical_section(self):
        self.assertEqual(self.sample(0xffffffff,128,128,17,0,1),17)
        self.assertEqual(self.sample(0xffffffff,0,0,0,0),(-4500)&0xffffffff)
if __name__=='__main__':unittest.main()
