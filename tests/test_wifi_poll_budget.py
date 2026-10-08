"""Actual wait and selector: bounded CPU spins and inactive-AP mutation guard."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Budget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=(ROOT/'src/sdio.c').read_text();a=s.index('static void read_wait(')
        wait=s[a:s.index('\nstatic int transfer_wait',a)]
        a=s.index('void sdio_wifi_poll_budget(')
        selector=s[a:s.index('\nvoid sdio_wifi_read_polling(',a)]
        harness=r'''
static unsigned wifi_poll_budget=64,wifi_wait_spins,wifi_wait_yields;
static unsigned wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending,delays;
static void vTaskDelay(unsigned n){delays+=n;}
static void field(const char *s,unsigned n){(void)s;(void)n;}
static void uart_puts(const char *s){(void)s;}
void reset(void){wifi_poll_budget=64;wifi_wait_spins=wifi_wait_yields=delays=0;
    wifi_ap_active=wifi_peer_state=wifi_peer_activate_pending=0;}
void active(unsigned a,unsigned p,unsigned pending){wifi_ap_active=a;wifi_peer_state=p;wifi_peer_activate_pending=pending;}
unsigned state(unsigned n){unsigned v[]={wifi_poll_budget,wifi_wait_spins,wifi_wait_yields,delays};return v[n];}
'''
        wrappers='\nvoid step(unsigned calls,unsigned fast){unsigned polls=0;for(unsigned i=0;i<calls;i++)read_wait(&polls,fast);}\n'
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'budget.c').write_text(harness+wait+selector+wrappers)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'budget.c'),'-o',str(p/'budget.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'budget.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def state(self):return [self.c.state(i) for i in range(4)]
    def test_both_spin_budgets_yield_periodically(self):
        for budget in (64,4096):
            self.c.reset()
            if budget==4096:self.c.sdio_wifi_poll_budget()
            self.c.step(budget*3+1,1)
            self.assertEqual(self.state(),[budget,3*(budget-1)+1,3,3])
    def test_slow_wait_always_yields_even_with_large_budget(self):
        self.c.reset();self.c.sdio_wifi_poll_budget();self.c.step(130,0)
        self.assertEqual(self.state(),[4096,0,130,130])
    def test_selection_refuses_all_active_states_without_resetting_metrics(self):
        for flags in ((1,0,0),(0,3,0),(0,0,1)):
            self.c.reset();self.c.step(65,1);before=self.state()
            self.c.active(*flags);self.c.sdio_wifi_poll_budget();self.assertEqual(self.state(),before)
        self.c.active(0,0,0);self.c.sdio_wifi_poll_budget()
        self.assertEqual(self.state(),[4096,0,0,1])
        self.c.sdio_wifi_poll_budget();self.assertEqual(self.state(),[64,0,0,1])
