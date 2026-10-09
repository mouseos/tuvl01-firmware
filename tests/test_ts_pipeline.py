"""Execute the actual two-buffer pipeline with delayed DMA and credit stalls."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=(ROOT/'src/tuner_ts.c').read_text();a=s.index('static uint8_t pipe_packets[2]')
        body=s[a:s.index('\nint tuner_ts_stream_poll',a)]
        harness=r"""
#include <stdint.h>
#include <string.h>
typedef uint32_t TickType_t;
#define TUNER_TS_PACKET 188U
#define TUNER_TS_MAX_PACKETS 32U
static unsigned streaming,pending,position,sequence,packet_index,stream_flags,stream_over,stream_under,stream_busy;
static unsigned stream_read_ticks,stream_tx_ticks,stream_burst=1,stream_aggregate=1,stream_frame_packets=7;
static unsigned stream_dma_reads,stream_dma_ticks;
static unsigned stream_pipeline,dma_verified=1,dma_long_verified=1,ccr;
#define R32(a) ccr
static struct {unsigned active;TickType_t start;} ts_dma;
static uint8_t *dma_buffer;
static int done,fifo=1,send_result=1;
static unsigned starts,finishes,sends,stops,syncs,violations,tick,generation,recv_flags[64],recv_values[64];
static TickType_t xTaskGetTickCount(void){return tick++;}
static void uart_puts(const char *s){(void)s;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static int dma_start(const uint8_t *tx,uint8_t *rx,unsigned n,unsigned inc,unsigned wide){
 (void)tx;(void)n;(void)inc;(void)wide;if(ts_dma.active)return -1;
 ts_dma.active=1;dma_buffer=rx;starts++;return 0;
}
static int dma_poll(void){if(done==1)memset(dma_buffer,++generation,6016);return done;}
static int dma_finish(int result,unsigned report){(void)report;ts_dma.active=0;finishes++;return result;}
static int end(void){return 0;}
static int begin(void){if(ts_dma.active)violations++;return 0;}
static int exchange(uint8_t tx,uint8_t *rx){(void)tx;*rx=0;return 0;}
static int failure(void){return -1;}
static int status(uint8_t r[5]){if(ts_dma.active)violations++;r[4]=0;return 0;}
static int tuner_ts_classify(uint8_t v){(void)v;return fifo;}
static int synchronize_quiet(unsigned q){(void)q;syncs++;return 0;}
static void stream_pipeline_abort(void);
static void tuner_ts_stream_stop(void){stream_pipeline_abort();streaming=pending=position=0;stops++;}
static int sdio_wifi_ts_pair(const uint8_t *p,unsigned n,unsigned seq,unsigned index,unsigned flags){
 (void)seq;(void)index;
 if(ts_dma.active && (uintptr_t)p>=(uintptr_t)dma_buffer && (uintptr_t)p<(uintptr_t)dma_buffer+6016)violations++;
 recv_flags[sends]=flags;recv_values[sends]=p[0];sends++;
 return send_result==1?(int)n:send_result;
}
static int sdio_wifi_ts(const uint8_t *p,unsigned n,unsigned s,unsigned i,unsigned f){return sdio_wifi_ts_pair(p,n,s,i,f);}
"""
        exports=r"""
void reset(void){
 ts_dma.active=0;stream_pipeline_abort();streaming=1;stream_pipeline=1;
 pending=position=sequence=packet_index=stream_flags=stream_over=stream_under=stream_busy=0;
 stream_read_ticks=stream_tx_ticks=starts=finishes=sends=stops=syncs=violations=tick=generation=0;
 done=0;fifo=send_result=1;memset(pipe_packets,0,sizeof pipe_packets);
}
int poll(void){return streaming?stream_pipeline_poll():0;}
void complete(int result){done=result;}
void credit(int result){send_result=result;}
void input(int result){fifo=result;}
void stop(void){tuner_ts_stream_stop();}
unsigned get(unsigned i){unsigned v[]={starts,finishes,sends,stops,violations,packet_index,position,pending,pipe_current,pipe_inflight,pipe_ready,stream_over,stream_busy,ts_dma.active,syncs};return v[i];}
unsigned trace(unsigned i,unsigned which){return which?recv_flags[i]:recv_values[i];}
"""
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'pipe.c').write_text(harness+body+exports)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'pipe.c'),'-o',str(p/'pipe.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'pipe.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_delayed_dma_never_sends_inflight_buffer_and_alternates_buffers(self):
        self.c.reset();self.assertEqual(self.c.poll(),0);self.assertEqual(self.c.get(2),0)
        self.c.poll();self.assertEqual(self.c.get(0),1);self.assertEqual(self.c.get(2),0)
        self.c.complete(1);self.assertEqual(self.c.poll(),1)
        self.assertEqual([self.c.get(i) for i in [0,1,2,4,5]],[2,1,3,0,32])
        self.assertEqual([self.c.trace(i,0) for i in range(3)],[1]*3)
        self.c.poll();self.assertEqual(self.c.get(5),64)
        self.assertEqual([self.c.trace(i,0) for i in range(3,6)],[2]*3)
        self.assertEqual(self.c.get(4),0)
    def test_credit_stall_keeps_current_and_completed_next_without_overwrite(self):
        self.c.reset();self.c.poll();self.c.complete(1);self.c.credit(0)
        self.assertEqual(self.c.poll(),0);self.c.poll()
        self.assertEqual(self.c.get(0),2);self.assertEqual(self.c.get(10),1)
        self.assertEqual(self.c.get(8),0);self.assertEqual(self.c.get(5),0)
        self.c.credit(1);self.c.poll();self.assertEqual(self.c.get(5),32)
        self.c.poll();self.assertEqual(self.c.get(5),64);self.assertEqual(self.c.get(4),0)
    def test_fifo_resync_marks_next_acquired_buffer_not_current_data(self):
        self.c.reset();self.c.poll();self.c.complete(1);self.c.input(-3);self.c.poll()
        self.assertEqual(self.c.get(11),1);self.assertEqual(self.c.get(14),1)
        self.assertEqual([self.c.trace(i,1) for i in range(3)],[0]*3)
        self.c.input(1);self.c.poll();self.c.poll()
        self.assertEqual(self.c.trace(3,1),1);self.assertEqual(self.c.trace(4,1),0)
    def test_stop_and_uncertain_write_abort_dma_before_recovery(self):
        self.c.reset();self.c.poll();self.c.stop();self.assertEqual(self.c.get(13),0)
        self.assertEqual([self.c.get(i) for i in [8,9,10]],[2,2,2])
        self.c.reset();self.c.poll();self.c.complete(1);self.c.credit(-1);self.c.poll()
        self.assertEqual(self.c.get(3),1);self.assertEqual(self.c.get(13),0)
        sends=self.c.get(2);self.c.poll();self.assertEqual(self.c.get(2),sends)
    def test_dma_failure_and_reserved_fifo_stop_without_transmitting(self):
        self.c.reset();self.c.poll();self.c.complete(-1);self.c.poll()
        self.assertEqual(self.c.get(3),1);self.assertEqual(self.c.get(2),0)
        self.c.reset();self.c.input(-4);self.c.poll()
        self.assertEqual(self.c.get(3),1);self.assertEqual(self.c.get(0),0)
if __name__=='__main__':unittest.main()
