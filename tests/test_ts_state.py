"""Idle diagnostic compiles against read-only MMIO and refuses active transfers."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class State(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/tuner_ts.c').read_text()
        registers=source[source.index('static void registers(void){'):source.index('static int wait_status(')]
        body=source[source.index('void tuner_ts_state(void){'):source.index('static int status(')]
        harness=r'''
#include <stdint.h>
#include <string.h>
static unsigned streaming,ready,dma_verified=1,dma_long_verified=1,stream_pipeline,stream_test_source,spi_divider;
static struct {unsigned active;} ts_dma;
static unsigned reads,fields,result;
static unsigned mmio(uintptr_t address){++reads;return address&255;}
/* Values, never lvalues: a register write in the diagnostic will not compile. */
#define R8(a) mmio(a)
#define R16(a) mmio(a)
#define R32(a) mmio(a)
#define S(n) R8(0xffff8800U+(n))
#define DMA(n,o) R32(0xfffe1000U+16U*(n)+(o))
#define DMAOR R16(0xfffe1200U)
#define DMARS0 R16(0xfffe1300U)
static void field(const char *name,unsigned value){(void)name;(void)value;++fields;}
static void uart_puts(const char *s){
 if(!strcmp(s,"TS state end status=read\n"))result=1;
 if(!strcmp(s,"TS state end status=refused-active\n"))result=2;
 if(!strcmp(s,"TS state end status=refused-uninitialized\n"))result=3;
}
void reset(unsigned flags){ready=flags&1;streaming=(flags>>1)&1;ts_dma.active=(flags>>2)&1;reads=fields=result=0;}
unsigned software(void){return ready|(streaming<<1)|(ts_dma.active<<2);}
unsigned get(unsigned index){unsigned values[]={reads,fields,result};return values[index];}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'state.c').write_text(harness+registers+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'state.c'),'-o',str(p/'state.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'state.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_idle_snapshot_preserves_software_and_uses_read_only_registers(self):
        self.c.reset(1);self.c.tuner_ts_state()
        self.assertEqual(self.c.software(),1)
        self.assertEqual([self.c.get(n) for n in range(3)],[17,23,1])
    def test_active_or_uninitialized_refusal_never_touches_mmio(self):
        for flags in range(8):
            if flags==1:continue
            self.c.reset(flags);self.c.tuner_ts_state()
            self.assertEqual(self.c.software(),flags)
            self.assertEqual([self.c.get(n) for n in range(3)],[0,0,2 if flags&6 else 3])
if __name__=='__main__':unittest.main()
