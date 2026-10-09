"""Exercise the actual clock selector with transfer-state and readback failures."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ClockProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src=(ROOT/'src/sdio.c').read_text()
        function=src[src.index('void sdio_wifi_clock_profile(void){'):src.index('void sdio_wifi_width(void){')]
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        flags=['wifi_ap_active','wifi_peer_state','wifi_peer_activate_pending','wifi_management_pending',
               'wifi_data_count','wifi_bench_active','wifi_sink_active','wifi_scan_active','wifi_scan_unresolved',
               'wifi_ais_retained_active','wifi_connection_unresolved']
        mock='''#include <stdint.h>
#include <string.h>
static unsigned card_verified,wifi_hif_ready,wifi_tx_fault,stream,reads,accesses,fail,wrong;
static uint16_t clockreg;static char output[2048];
static struct {unsigned pending;} wifi_feedback;static struct {unsigned active;} wifi_bench_io;
static uint16_t* reg(unsigned offset){(void)offset;accesses++;return &clockreg;}
#define S(x) (*reg(x))
static void vTaskDelay(unsigned n){(void)n;}
static unsigned tuner_ts_stream_active(void){return stream;}
static void uart_puts(const char*s){strncat(output,s,sizeof output-strlen(output)-1);}
static void field(const char*s,unsigned n){(void)n;uart_puts(s);}
static int radio_read(unsigned offset,uint32_t* value){(void)offset;++reads;*value=reads==wrong?0:0x5931;return reads==fail?-1:0;}
'''+''.join('static unsigned '+f+';\n' for f in flags)+function+'''
void setup(unsigned mask,unsigned state,unsigned clock,unsigned failure,unsigned mismatch){
card_verified=state&1;wifi_hif_ready=state&2;wifi_tx_fault=state&4;
clockreg=clock;reads=accesses=0;fail=failure;wrong=mismatch;output[0]=0;
'''+''.join(f'{f}=(mask>>{i})&1;\n' for i,f in enumerate(flags))+'''
wifi_feedback.pending=(mask>>11)&1;wifi_bench_io.active=(mask>>12)&1;stream=(mask>>13)&1;
}
unsigned final_clock(void){return clockreg;}unsigned read_count(void){return reads;}
unsigned mmio_count(void){return accesses;}const char* log_output(void){return output;}
'''
        (p/'clock.c').write_text(mock)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'clock.c'),'-o',str(p/'clock.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'clock.so'));cls.c.log_output.restype=ctypes.c_char_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_clock(self,mask=0,state=3,clock=0x101,failure=0,mismatch=0):
        self.c.setup(mask,state,clock,failure,mismatch);self.c.sdio_wifi_clock_profile()
        return self.c.log_output().decode()
    def test_both_proven_profiles_require_two_chip_reads(self):
        for before,after in [(0x101,0x180),(0x180,0x101)]:
            self.assertIn('status=ready',self.run_clock(clock=before))
            self.assertEqual(self.c.final_clock(),after);self.assertEqual(self.c.read_count(),2)
    def test_each_active_owner_refuses_without_mmio(self):
        for bit in range(14):
            with self.subTest(bit=bit):
                self.assertIn('status=refused-active',self.run_clock(mask=1<<bit))
                self.assertEqual(self.c.mmio_count(),0);self.assertEqual(self.c.read_count(),0)
    def test_unverified_card_hif_or_fault_refuses_without_mmio(self):
        for state in (0,1,2,7):
            self.assertIn('status=refused-state',self.run_clock(state=state))
            self.assertEqual(self.c.mmio_count(),0)
    def test_unknown_or_disabled_clock_is_preserved(self):
        for clock in (0,1,0x80,0x100,0x102,0xffff):
            self.assertIn('status=refused-clock',self.run_clock(clock=clock))
            self.assertEqual(self.c.final_clock(),clock);self.assertEqual(self.c.read_count(),0)
    def test_each_read_or_identity_failure_restores_previous_clock(self):
        for clock in (0x101,0x180):
            for nth in (1,2):
                for name in ('failure','mismatch'):
                    with self.subTest(clock=clock,nth=nth,name=name):
                        self.assertIn('status=failed',self.run_clock(clock=clock,**{name:nth}))
                        self.assertEqual(self.c.final_clock(),clock)
