"""Actual IRQ wait/ISR with modeled hardware and FreeRTOS notification races."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class IRQ(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'board.h').write_text('#include <stdint.h>\nvolatile uint16_t *reg(unsigned long);\n#define R16(a) (*reg(a))\n')
        (p/'FreeRTOS.h').write_text('typedef unsigned TickType_t;typedef int BaseType_t;typedef void *TaskHandle_t;\n#define pdTRUE 1\n#define pdFALSE 0\nvoid enter(void),leave(void);\n#define taskENTER_CRITICAL() enter()\n#define taskEXIT_CRITICAL() leave()\n')
        (p/'task.h').write_text('TaskHandle_t xTaskGetCurrentTaskHandle(void);\nunsigned ulTaskNotifyTake(int,unsigned);\nvoid vTaskNotifyGiveFromISR(TaskHandle_t,BaseType_t *);\nvoid vTaskSwitchContext(void);\nTickType_t xTaskGetTickCount(void);\n')
        harness=r'''
#include <stdint.h>
#include "FreeRTOS.h"
#include "sdio_irq.h"
static volatile uint16_t regs[128],priority;
static unsigned notifications,depth,inject,mode,block_calls,notify_calls,switches;
static unsigned event1,event2,last_mask1,last_mask2,last_ticks;
static unsigned valid_owner=1;
volatile uint16_t *reg(unsigned long a){return a==0xfffe0c1e?&priority:&regs[(a-0xffffc800)/2];}
static void event(void){
    regs[0x1c/2]|=event1;regs[0x1e/2]|=event2;
    last_mask1=regs[0x20/2];last_mask2=regs[0x22/2];sdio_irq_handler();
}
void enter(void){depth++;}
void leave(void){depth--;if(!depth && inject && (regs[0x20/2]!=0x03bd || regs[0x22/2]!=0x837f)){
    inject=0;event();}}
TaskHandle_t xTaskGetCurrentTaskHandle(void){return valid_owner?(void *)1:0;}
unsigned ulTaskNotifyTake(int clear,unsigned ticks){
    (void)clear;
    if(ticks){block_calls++;last_ticks=ticks;if(mode==1 && !notifications)event();}
    unsigned n=notifications;notifications=0;return n;
}
void vTaskNotifyGiveFromISR(TaskHandle_t t,BaseType_t *w){
    if(t==(void *)1){notifications++;notify_calls++;*w=1;}
}
void vTaskSwitchContext(void){switches++;}
void reset(unsigned how,unsigned before,unsigned i1,unsigned i2){
    sdio_irq_set(0);for(unsigned i=0;i<128;i++)regs[i]=0;
    notifications=depth=block_calls=notify_calls=switches=last_ticks=0;
    event1=i1;event2=i2;mode=how;inject=before;valid_owner=1;priority=0xa05a;
    sdio_irq_set(1);
}
void pending(unsigned a,unsigned b){regs[0x1c/2]=a;regs[0x1e/2]=b;}
void stale(void){notifications=99;}
void no_owner(void){sdio_irq_set(0);valid_owner=0;}
unsigned state(unsigned n){unsigned a[]={regs[0x1c/2],regs[0x1e/2],regs[0x20/2],regs[0x22/2],
    priority,block_calls,notify_calls,switches,last_ticks,last_mask1,last_mask2};return a[n];}
'''
        source=(ROOT/'src/sdio.c').read_text();start=source.index('static int transfer_wait(')
        actual=source[start:source.index('\n/* Mode2',start)]
        extra=r'''
static unsigned clock_tick;
TickType_t xTaskGetTickCount(void){return clock_tick;}
static void read_wait(unsigned *p,unsigned f){(void)p;(void)f;}
static void status(void){}
static void uart_puts(const char *s){(void)s;}
'''
        wrapper='\nint transfer(unsigned now,unsigned start,unsigned limit){unsigned p=0;clock_tick=now;return transfer_wait(&p,0,1,0,start,limit);}\n'
        (p/'harness.c').write_text(harness+extra+actual+wrapper)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'include'),
            str(ROOT/'src/sdio_irq.c'),str(p/'harness.c'),'-o',str(p/'irq.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'irq.so'));cls.c.sdio_irq_wait.argtypes=[ctypes.c_uint]*3
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def counters(self):return [self.c.sdio_irq_counter(i) for i in range(6)]
    def test_pending_completion_and_error_never_block(self):
        for i1,i2 in ((1,0),(5,0),(0,0x8000)):
            self.c.reset(0,0,0,0);self.c.pending(i1,i2)
            self.assertEqual(self.c.sdio_irq_wait(1,0,100),0)
            self.assertEqual(self.c.state(5),0);self.assertEqual(self.counters(),[1,0,0,1,0,0])
            self.assertEqual(self.c.state(0),i1);self.assertEqual(self.c.state(1),i2)
    def test_notification_between_arm_and_block_is_retained(self):
        self.c.reset(0,1,1,0);self.c.stale()
        self.assertEqual(self.c.sdio_irq_wait(1,0,100),0)
        self.assertEqual(self.counters(),[1,1,1,0,0,0])
        self.assertEqual(self.c.state(6),1);self.assertEqual(self.c.state(7),1)
        self.assertEqual((self.c.state(2),self.c.state(3)),(0x03bd,0x837f))
    def test_fifo_wakeup_keeps_coalesced_dataend_for_owner(self):
        self.c.reset(1,0,4,0x100)
        self.assertEqual(self.c.sdio_irq_wait(0,0x100,1000),0)
        self.assertEqual((self.c.state(0),self.c.state(1)),(4,0x100))
        # BRE and errors are unmasked; BWE remains masked.
        self.assertEqual((self.c.state(9),self.c.state(10)),(0x03bd,0x200))
        self.assertEqual(self.c.state(8),1000)
        self.assertEqual(self.c.sdio_irq_wait(4,0,1000),0)
        self.assertEqual(self.counters(),[1,1,1,1,0,0])
    def test_timeout_and_late_disabled_irq_cannot_notify_owner(self):
        self.c.reset(0,0,0,0)
        self.assertEqual(self.c.sdio_irq_wait(1,0,3),-1)
        self.assertEqual(self.counters(),[1,0,1,0,1,0])
        self.assertEqual((self.c.state(2),self.c.state(3)),(0x03bd,0x837f))
        self.c.sdio_irq_set(0);self.c.pending(1,0);self.c.sdio_irq_handler()
        self.assertEqual(self.c.state(6),0);self.assertEqual(self.c.state(4),0xa05a)
        self.assertEqual(self.c.sdio_irq_wait(1,0,1),-1)
    def test_priority_preserves_other_fields_and_missing_owner_refuses_enable(self):
        self.c.reset(0,0,0,0);self.assertEqual(self.c.state(4),0xa15a)
        self.c.no_owner();self.assertEqual(self.c.sdio_irq_set(1),-1)
        self.assertEqual(self.c.sdio_irq_enabled(),0);self.assertEqual(self.c.state(4),0xa05a)
    def test_expired_deadline_does_not_underflow_into_a_long_wait(self):
        self.c.reset(1,0,1,0);self.assertEqual(self.c.transfer(100,0,100),-1)
        self.assertEqual(self.c.state(5),0)
    def test_wrapped_tick_deadline_passes_only_remaining_budget(self):
        self.c.reset(1,0,1,0);self.assertEqual(self.c.transfer(2,0xfffffffe,10),0)
        self.assertEqual(self.c.state(8),6)
