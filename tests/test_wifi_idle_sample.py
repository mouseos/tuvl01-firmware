"""Run the actual handoff function against ownership and bus failure states."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class IdleSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src=(ROOT/'src/sdio.c').read_text()
        function=src[src.index('void sdio_wifi_idle_sample('):src.index('void sdio_wifi_clock_profile(')]
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        flags=['wifi_ap_active','wifi_peer_state','wifi_peer_activate_pending','wifi_management_pending',
               'wifi_data_count','wifi_bench_active','wifi_sink_active','wifi_scan_active','wifi_scan_unresolved',
               'wifi_ais_retained_active','wifi_connection_unresolved']
        mock='''#include <stdint.h>
#include <string.h>
static unsigned card_verified,wifi_hif_ready,wifi_tx_fault,stream,own,reads,writes,mmio,samples,bad_order;
static unsigned fail_read,fail_write,reject_handoff,reject_wake;static uint16_t clockreg;
static struct {unsigned pending;} wifi_feedback;static struct {unsigned active;} wifi_bench_io;
static char output[4096];
static uint16_t* reg(unsigned o){(void)o;mmio++;return &clockreg;}
#define S(x) (*reg(x))
#define pdMS_TO_TICKS(x) (x)
static void vTaskDelay(unsigned n){(void)n;}
static unsigned tuner_ts_stream_active(void){return stream;}
static void uart_puts(const char*s){strncat(output,s,sizeof output-strlen(output)-1);}
static void field(const char*s,unsigned n){(void)n;uart_puts(s);}
static int radio_read(unsigned address,uint32_t*v){if(address!=4)bad_order++;reads++;*v=own;return reads==fail_read?-1:0;}
static int radio_write(unsigned address,uint32_t v){
 if(address!=4 || (v!=0x100 && v!=0x200))bad_order++;
 writes++;
 /* Failed handoff can still take effect; failed wake remains unowned. */
 if(v==0x100 && !reject_handoff)own=0;
 if(v==0x200 && !reject_wake && writes!=fail_write)own=0x100;
 return writes==fail_write?-1:0;
}
static int radio_wait(unsigned address,uint32_t mask,uint32_t reject){
 uint32_t v;if(address!=4 || mask!=0x100 || reject)bad_order++;
 return radio_read(address,&v) || !(v&mask)?-1:0;
}
static void sample(void){samples++;if(own)bad_order++;uart_puts("QUALITY end status=counts-raw\\n");}
'''+''.join('static unsigned '+f+';\n' for f in flags)+function+'''
void setup(unsigned active,unsigned state,unsigned initial,unsigned rf,unsigned wf,unsigned reject,unsigned wake){
card_verified=state&1;wifi_hif_ready=state&2;wifi_tx_fault=state&4;clockreg=state&8?0:0x101;
own=initial;reads=writes=mmio=samples=bad_order=0;fail_read=rf;fail_write=wf;reject_handoff=reject;reject_wake=wake;output[0]=0;
'''+''.join(f'{f}=(active>>{i})&1;\n' for i,f in enumerate(flags))+'''
wifi_feedback.pending=(active>>11)&1;wifi_bench_io.active=(active>>12)&1;stream=(active>>13)&1;
}
void run_sample(unsigned null_callback){sdio_wifi_idle_sample(null_callback?0:sample);}
unsigned metric(unsigned n){unsigned v[]={reads,writes,mmio,samples,bad_order,own,wifi_tx_fault,wifi_hif_ready};return v[n];}
const char* log_output(void){return output;}
'''
        (p/'idle.c').write_text(mock)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'idle.c'),'-o',str(p/'idle.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'idle.so'));cls.c.log_output.restype=ctypes.c_char_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_sample(self,active=0,state=3,initial=0x100,rf=0,wf=0,reject=0,wake=0,null=0):
        self.c.setup(active,state,initial,rf,wf,reject,wake);self.c.run_sample(null)
        self.assertEqual(self.c.metric(4),0)
        return self.c.log_output().decode()
    def test_sample_runs_only_with_fw_ownership_and_driver_is_restored(self):
        self.assertIn('status=restored',self.run_sample())
        self.assertEqual(self.c.metric(3),1);self.assertEqual(self.c.metric(5),0x100)
        self.assertEqual(self.c.metric(6),0);self.assertNotEqual(self.c.metric(7),0)
    def test_each_active_owner_is_refused_without_bus_or_mmio(self):
        for bit in range(14):
            self.assertIn('status=refused-active',self.run_sample(active=1<<bit))
            self.assertEqual(sum(self.c.metric(n) for n in (0,1,2,3)),0)
    def test_unverified_state_or_null_callback_never_accesses_hardware(self):
        for state,null in [(0,0),(1,0),(2,0),(7,0),(3,1)]:
            self.assertIn('status=refused-state',self.run_sample(state=state,null=null))
            self.assertEqual(sum(self.c.metric(n) for n in (0,1,2,3)),0)
    def test_disabled_clock_and_initial_fw_ownership_do_not_mutate(self):
        self.assertIn('status=refused-clock',self.run_sample(state=11))
        self.assertEqual(self.c.metric(1),0);self.assertEqual(self.c.metric(0),0)
        self.assertIn('status=refused-ownership',self.run_sample(initial=0))
        self.assertEqual(self.c.metric(1),0);self.assertEqual(self.c.metric(3),0)
    def test_read_failure_before_handoff_does_not_write_or_sample(self):
        self.assertIn('status=failed',self.run_sample(rf=1))
        self.assertEqual(self.c.metric(1),0);self.assertEqual(self.c.metric(3),0)
    def test_uncertain_handoff_write_and_read_always_reclaim_without_sampling(self):
        for params in ({'wf':1},{'rf':2}):
            self.assertIn('status=failed',self.run_sample(**params))
            self.assertEqual(self.c.metric(3),0);self.assertEqual(self.c.metric(5),0x100)
    def test_refused_handoff_does_not_sample_and_leaves_driver_owned(self):
        self.assertIn('status=refused-handoff',self.run_sample(reject=1))
        self.assertEqual(self.c.metric(3),0);self.assertEqual(self.c.metric(5),0x100)
    def test_each_wake_failure_blocks_further_hif_use(self):
        for params in ({'wf':2},{'rf':3},{'rf':4},{'wake':1}):
            self.assertIn('status=wake-failed',self.run_sample(**params))
            self.assertEqual(self.c.metric(6),1);self.assertEqual(self.c.metric(7),0)
