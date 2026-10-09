"""Execute the actual stream-poll body with deterministic bus/credit failures."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Burst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/tuner_ts.c').read_text()
        start=source.index('int tuner_ts_stream_poll(void){')
        body=source[start:source.index('\nvoid tuner_ts_benchmark',start)]
        harness=r'''
#include <stdint.h>
typedef uint32_t TickType_t;
static uint8_t packets[32*188];
static unsigned streaming,pending,position,sequence,packet_index,stream_flags,stream_over,stream_under,stream_busy;
static unsigned stream_read_ticks,stream_tx_ticks,stream_poll_ticks,stream_burst,stream_aggregate,stream_test_source;
static unsigned stream_frame_packets=7;
static unsigned stream_pipeline;
static int stream_pipeline_poll(void){return 0;}
static unsigned tick,reads,calls,stops;
static int replies[16];
static unsigned sizes[16],offsets[16],sequences[16],indices[16],flags[16];
static TickType_t xTaskGetTickCount(void){return tick++;}
static int read_packets(uint8_t *p,unsigned n,unsigned quiet){(void)p;(void)quiet;reads++;return n;}
static int synchronize_quiet(unsigned q){(void)q;return 0;}
static void uart_puts(const char *s){(void)s;}
static void tuner_ts_stream_stop(void){streaming=0;pending=position=0;stops++;}
static int sdio_wifi_ts(const uint8_t *p,unsigned n,unsigned seq,unsigned index,unsigned flag){
    unsigned at=calls++;sizes[at]=n;offsets[at]=(unsigned)(p-packets);
    sequences[at]=seq;indices[at]=index;flags[at]=flag;return replies[at];
}
void reset(unsigned burst){
    streaming=1;pending=position=sequence=packet_index=stream_over=stream_under=stream_busy=0;
    stream_flags=1;stream_burst=burst;stream_aggregate=stream_test_source=0;tick=reads=calls=stops=0;
    stream_frame_packets=7;
    for(unsigned i=0;i<16;i++){replies[i]=1;sizes[i]=offsets[i]=sequences[i]=indices[i]=flags[i]=0;}
}
void reply(unsigned i,int value){replies[i]=value;}
void aggregate(void){stream_aggregate=1;}
void synthetic(void){stream_test_source=1;}
void frame_size(unsigned n){stream_frame_packets=n;}
static int sdio_wifi_ts_pair(const uint8_t *p,unsigned n,unsigned seq,unsigned index,unsigned flag){
    int r=sdio_wifi_ts(p,n,seq,index,flag);return r==1?(int)n:r;
}
unsigned state(unsigned i){unsigned values[]={calls,reads,stops,pending,position,sequence,packet_index,stream_busy,streaming};return values[i];}
unsigned trace(unsigned i,unsigned field){return field==0?sizes[i]:field==1?offsets[i]:field==2?sequences[i]:field==3?indices[i]:flags[i];}
'''
        cls.tmp=tempfile.TemporaryDirectory();path=pathlib.Path(cls.tmp.name)
        (path/'stream.c').write_text(harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Wno-unused-variable','-Werror',
            str(path/'stream.c'),'-o',str(path/'stream.so')],check=True)
        cls.lib=ctypes.CDLL(str(path/'stream.so'))
        cls.lib.state.restype=cls.lib.trace.restype=ctypes.c_uint
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def states(self):return [self.lib.state(i) for i in range(9)]
    def test_default_sends_one_and_burst_stops_at_existing_batch_boundary(self):
        self.lib.reset(0);self.assertEqual(self.lib.tuner_ts_stream_poll(),0)
        self.assertEqual(self.states(),[1,1,0,32,7,1,7,0,1])
        self.lib.reset(1);self.assertEqual(self.lib.tuner_ts_stream_poll(),1)
        self.assertEqual(self.states(),[5,1,0,0,0,5,32,0,1])
        self.assertEqual([self.lib.trace(i,0) for i in range(5)],[7,7,7,7,4])
    def test_synthetic_source_bypasses_tuner_and_preserves_credit_stall_position(self):
        self.lib.reset(1);self.lib.synthetic();self.lib.reply(2,0)
        self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[3,0,0,32,14,2,14,1,1])
        self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[6,0,0,0,0,5,32,1,1])
        self.assertEqual([self.lib.trace(i,1) for i in range(6)],[0,1316,2632,2632,3948,5264])
    def test_small_frames_preserve_batch_tail_and_stalled_sequence(self):
        self.lib.reset(0);self.lib.frame_size(1);self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[1,1,0,32,1,1,1,0,1])
        self.lib.reset(0);self.lib.frame_size(3);self.lib.reply(2,0)
        for _ in range(12):self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[12,1,0,0,0,11,32,1,1])
        self.assertEqual([self.lib.trace(i,0) for i in range(12)],[3]*11+[2])
        self.assertEqual([self.lib.trace(i,2) for i in range(12)],[0,1,2,2,3,4,5,6,7,8,9,10])
        self.assertEqual([self.lib.trace(i,1) for i in range(12)],[188*n for n in (0,3,6,6,9,12,15,18,21,24,27,30)])
    def test_credit_stall_resumes_without_duplicate_packets_or_sequence_increment(self):
        self.lib.reset(1);self.lib.reply(2,0);self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[3,1,0,32,14,2,14,1,1])
        self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[6,1,0,0,0,5,32,1,1])
        self.assertEqual([self.lib.trace(i,1) for i in range(6)],[0,1316,2632,2632,3948,5264])
        self.assertEqual([self.lib.trace(i,2) for i in range(6)],[0,1,2,2,3,4])
        self.assertEqual([self.lib.trace(i,4) for i in range(6)],[1,0,0,0,0,0])
    def test_mid_batch_failure_stops_immediately_and_does_not_send_again(self):
        self.lib.reset(1);self.lib.reply(1,-1);self.assertEqual(self.lib.tuner_ts_stream_poll(),0)
        self.assertEqual(self.states(),[2,1,1,0,0,1,7,0,0])
        self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[2,1,1,0,0,1,7,0,0])
    def test_aggregate_accounts_for_each_contained_datagram(self):
        self.lib.reset(0);self.lib.aggregate();self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[1,1,0,32,14,2,14,0,1])
        self.lib.reset(1);self.lib.aggregate();self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[3,1,0,0,0,5,32,0,1])
        self.assertEqual([self.lib.trace(i,0) for i in range(3)],[14,14,4])
        self.assertEqual([self.lib.trace(i,2) for i in range(3)],[0,2,4])
    def test_aggregate_short_credit_stall_and_uncertain_write(self):
        self.lib.reset(0);self.lib.aggregate();self.lib.reply(0,7)
        self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[1,1,0,32,7,1,7,0,1])
        self.lib.reply(1,0);self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[2,1,0,32,7,1,7,1,1])
        self.lib.reply(2,-1);self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[3,1,1,0,0,1,7,1,0])
        self.lib.tuner_ts_stream_poll()
        self.assertEqual(self.states(),[3,1,1,0,0,1,7,1,0])
    def test_partial_progress_then_credit_stall_requires_service_wait(self):
        self.lib.reset(1);self.lib.reply(2,0)
        self.assertEqual(self.lib.tuner_ts_stream_poll(),0)
        self.assertEqual(self.lib.state(6),14)
        self.assertEqual(self.lib.tuner_ts_stream_poll(),1)
if __name__=='__main__':unittest.main()
