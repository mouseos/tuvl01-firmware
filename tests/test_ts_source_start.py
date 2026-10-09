"""Exercise actual start/selector bodies and prove test mode skips tuner I/O."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class SourceStart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/tuner_ts.c').read_text();start=source.index('void tuner_ts_stream_start(void){')
        body=source[start:source.index('\nvoid tuner_ts_stream_burst',start)]
        harness=r'''
#include <stdint.h>
#include "ts_check.h"
static struct ts_check stream_input;
static uint8_t packets[32*188];
static unsigned streaming,pending,position,sequence,packet_index,stream_flags,stream_over,stream_under,stream_busy;
static unsigned stream_read_ticks,stream_tx_ticks,stream_poll_ticks,stream_test_source;
static unsigned stream_frame_packets=7,stream_aggregate,stream_burst;
static unsigned stream_pipeline,dma_verified,dma_long_verified;
static unsigned stream_dma_reads,stream_dma_ticks;
static unsigned stream_pattern_checks,stream_pattern_errors,stream_pattern_first;
static void stream_dma_pattern_prepare(void){}
static uint32_t ccr;
#define R32(a) ccr
static void stream_pipeline_abort(void){}
static unsigned reads,syncs,fills,bad_read;
static void sdio_wifi_io_start(void){}
static void uart_puts(const char *s){(void)s;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static int tuner_read_register(unsigned bank,unsigned reg,uint8_t *v){
 (void)bank;(void)reg;reads++;*v=0x10;return bad_read?-1:0;
}
static int synchronize_quiet(unsigned quiet){(void)quiet;syncs++;return 0;}
static unsigned ts_pattern_fill(uint8_t *out,unsigned capacity){(void)out;(void)capacity;fills++;return 32;}
void reset(unsigned source,unsigned active,unsigned bad){
 stream_pipeline=0;
 stream_test_source=source;streaming=active;bad_read=bad;reads=syncs=fills=0;
 sequence=17;packet_index=99;
}
unsigned state(unsigned i){unsigned s[]={streaming,stream_test_source,reads,syncs,fills,sequence,packet_index};return s[i];}
void pipeline(unsigned dma,unsigned wide,unsigned cache){stream_pipeline=1;dma_verified=dma;dma_long_verified=wide;ccr=cache;}
'''
        cls.tmp=tempfile.TemporaryDirectory();path=pathlib.Path(cls.tmp.name)
        (path/'start.c').write_text(harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-iquote'+str(ROOT/'include'),str(path/'start.c'),str(ROOT/'src/ts_check.c'),'-o',str(path/'start.so')],check=True)
        cls.lib=ctypes.CDLL(str(path/'start.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def state(self):return [self.lib.state(i) for i in range(7)]
    def test_live_requires_tuner_read_and_sync_while_test_source_skips_them(self):
        self.lib.reset(0,0,0);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[1,0,1,1,0,0,0])
        self.lib.reset(1,0,1);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[1,1,0,0,1,0,0])
    def test_failed_live_start_and_active_restart_do_not_reset_packet_sequence(self):
        self.lib.reset(0,0,1);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[0,0,1,0,0,17,99])
        self.lib.reset(1,1,0);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[1,1,0,0,0,17,99])
    def test_source_selection_refused_active_then_restores_live(self):
        self.lib.reset(1,1,0);self.lib.tuner_ts_stream_test_source()
        self.assertEqual(self.state(),[1,1,0,0,0,17,99])
        self.lib.reset(1,0,0);self.lib.tuner_ts_stream_test_source()
        self.assertEqual(self.state(),[0,0,0,0,0,17,99])
    def test_pipeline_live_start_requires_verified_long_dma_and_uncached_data(self):
        for dma,wide,cache in [(0,1,0),(1,0,0),(1,1,1)]:
            self.lib.reset(0,0,0);self.lib.pipeline(dma,wide,cache);self.lib.tuner_ts_stream_start()
            self.assertEqual(self.state(),[0,0,0,0,0,17,99])
        self.lib.reset(0,0,0);self.lib.pipeline(1,1,0);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[1,0,1,1,0,0,0])
    def test_dma_source_requires_pipeline_and_skips_tuner_io(self):
        self.lib.reset(2,0,1);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[0,2,0,0,0,17,99])
        for dma,wide,cache in [(0,1,0),(1,0,0),(1,1,1)]:
            self.lib.reset(2,0,1);self.lib.pipeline(dma,wide,cache);self.lib.tuner_ts_stream_start()
            self.assertEqual(self.state(),[0,2,0,0,0,17,99])
        self.lib.reset(2,0,1);self.lib.pipeline(1,1,0);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[1,2,0,0,1,0,0])
    def test_plain_source_selection_from_dma_source_is_valid(self):
        self.lib.reset(2,0,0);self.lib.tuner_ts_stream_test_source()
        self.assertEqual(self.state()[1],1)
    def test_fixed_source_guard_and_tuner_bypass(self):
        self.lib.reset(3,0,1);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[0,3,0,0,0,17,99])
        self.lib.reset(3,0,1);self.lib.pipeline(1,1,0);self.lib.tuner_ts_stream_start()
        self.assertEqual(self.state(),[1,3,0,0,1,0,0])
if __name__=='__main__':unittest.main()
