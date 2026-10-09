"""Run the actual DMA engine against a register model, including abort/ownership."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class AsyncDMA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=(ROOT/'src/tuner_ts.c').read_text();a=s.index('struct ts_dma_state {')
        body=s[a:s.index('\nvoid tuner_ts_dma_probe',a)]
        harness=r"""
#include <stdint.h>
#include <string.h>
typedef uint32_t TickType_t;
#define pdMS_TO_TICKS(x) (x)
static uint8_t r8[65536];static uint16_t r16[32768];static uint32_t r32[16384];
static unsigned tick,cleanup_check,bad_order;static const char *phase;
static uint32_t *reg32(uintptr_t a){
 if(cleanup_check && (a==0xfffe100cU || a==0xfffe101cU) && (r8[0x8800]&0xa0))bad_order++;
 return &r32[(a&65535)/4];
}
#define R8(a) r8[(a)&65535]
#define R16(a) r16[((a)&65535)/2]
#define R32(a) (*reg32(a))
#define S(n) R8(0xffff8800U+(n))
#define DMA(n,o) R32(0xfffe1000U+16U*(n)+(o))
#define DMAOR R16(0xfffe1200U)
#define DMARS0 R16(0xfffe1300U)
static TickType_t xTaskGetTickCount(void){return tick;}
static int wait_status(unsigned mask,const char *name){(void)mask;(void)name;return 0;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static void uart_puts(const char *s){(void)s;}
"""
        exports=r"""
void reset(uint32_t start){
 memset(r8,0,sizeof r8);memset(r16,0,sizeof r16);memset(r32,0,sizeof r32);
 ts_dma=(struct ts_dma_state){0};tick=start;cleanup_check=bad_order=0;
 S(0)=0x48;S(11)=0x20;S(32)=0;R16(0xffff8810U)=0xe780;
 R8(0xfffe0018U)=0xa0;DMARS0=0x1234;DMAOR=0x100;
}
int start(unsigned wide){return dma_start((const uint8_t *)0x1c000400U,(uint8_t *)0x1c000800U,6016,0,wide);}
int invalid(unsigned which){return dma_start((const uint8_t *)(uintptr_t)(which?0x1c000401U:0x1bffffffU),(uint8_t *)0x1c000800U,6016,0,1);}
int poll(void){return dma_poll();}
void advance(unsigned n){tick+=n;}
void complete(unsigned both,unsigned count){DMA(0,12)|=2;DMA(0,8)=count;if(both){DMA(1,12)|=2;DMA(1,8)=count;}}
void busy(void){DMA(7,12)=1;}
void error(unsigned which){if(which)S(3)=1;else DMAOR|=2;}
int finish(unsigned cancel){cleanup_check=1;int r=dma_finish(cancel?-1:0,0);cleanup_check=0;return r;}
unsigned get(unsigned i){unsigned v[]={ts_dma.active,S(0),S(11),S(32),R16(0xffff8810U),R8(0xfffe0018U),DMAOR,DMARS0,DMA(0,12),DMA(1,12),DMA(0,8),DMA(1,8),DMA(7,12),bad_order};return v[i];}
int synchronous(void){return dma_exchange((const uint8_t *)0x1bffffffU,(uint8_t *)0x1c000800U,128,0,0);}
"""
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'dma.c').write_text(harness+body+exports)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'dma.c'),'-o',str(p/'dma.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'dma.so'));cls.c.reset.argtypes=[ctypes.c_uint32]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def state(self):return [self.c.get(i) for i in range(14)]
    def test_completion_requires_both_channels_and_zero_counts_then_restores_state(self):
        for wide in [0,1]:
            self.c.reset(10);self.assertEqual(self.c.start(wide),0)
            self.assertEqual(self.c.get(10),6016//(4 if wide else 1))
            self.assertEqual(self.c.poll(),0);self.c.complete(0,0);self.assertEqual(self.c.poll(),0)
            self.c.complete(1,0);self.assertEqual(self.c.poll(),1);self.assertEqual(self.c.finish(0),0)
            self.assertEqual(self.state()[:10],[0,0x48,0x20,0,0xe780,0xa0,0x100,0x1234,0,0])
            self.assertEqual(self.c.get(13),0)
    def test_busy_dma_or_invalid_buffers_never_borrow_channels(self):
        self.c.reset(0);self.c.busy();before=self.state();self.assertEqual(self.c.start(1),-1)
        self.assertEqual(self.state(),before)
        for which in [0,1]:
            self.c.reset(0);before=self.state();self.assertEqual(self.c.invalid(which),-1);self.assertEqual(self.state(),before)
        self.assertEqual(self.c.synchronous(),-1)
    def test_cancel_releases_request_before_channels_and_is_idempotent(self):
        self.c.reset(0);self.c.start(1);self.assertEqual(self.c.finish(1),-1)
        self.assertEqual(self.state()[:10],[0,8,0x20,0,0xe780,0xa0,0x100,0x1234,0,0])
        before=self.state();self.c.finish(1);self.assertEqual(self.state(),before);self.assertEqual(self.c.get(13),0)
    def test_timeout_wrap_errors_and_bad_remaining_count_are_not_success(self):
        self.c.reset(0xfffffff0);self.c.start(1);self.c.advance(99);self.assertEqual(self.c.poll(),0)
        self.c.advance(1);self.assertEqual(self.c.poll(),-1);self.c.finish(1)
        for which in [0,1]:
            self.c.reset(0);self.c.start(1);self.c.error(which);self.assertEqual(self.c.poll(),-1);self.c.finish(1)
            if not which:self.assertEqual(self.c.get(6),0x102)
        self.c.reset(0);self.c.start(1);self.c.complete(1,1);self.assertEqual(self.c.poll(),-1)
    def test_second_start_does_not_modify_active_transfer(self):
        self.c.reset(0);self.c.start(1);before=self.state();self.assertEqual(self.c.start(1),-1);self.assertEqual(self.state(),before)
if __name__=='__main__':unittest.main()
