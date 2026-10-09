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
static uint8_t packets[32*188];
static unsigned streaming,pending,position,sequence,packet_index,stream_flags,stream_over,stream_under,stream_busy;
static unsigned stream_read_ticks,stream_tx_ticks,stream_poll_ticks,stream_test_source;
static unsigned stream_frame_packets=7,stream_aggregate,stream_burst;
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
 stream_test_source=source;streaming=active;bad_read=bad;reads=syncs=fills=0;
 sequence=17;packet_index=99;
}
unsigned state(unsigned i){unsigned s[]={streaming,stream_test_source,reads,syncs,fills,sequence,packet_index};return s[i];}
'''
        cls.tmp=tempfile.TemporaryDirectory();path=pathlib.Path(cls.tmp.name)
        (path/'start.c').write_text(harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(path/'start.c'),'-o',str(path/'start.so')],check=True)
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
if __name__=='__main__':unittest.main()
