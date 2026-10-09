"""A finite polling capture must not leave streaming DMA disabled afterward."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class PollCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/tuner_ts.c').read_text()
        body=source[source.index('void tuner_ts_capture_poll(void){'):source.index('void tuner_ts_probe(void){')]
        harness=r'''
static unsigned dma_verified,dma_long_verified,ready,failed,seen,calls,spi_divider;
void tuner_ts_capture(void){seen=dma_verified|(dma_long_verified<<1);calls++;if(failed)ready=0;}
void setup(unsigned flags,unsigned fail){dma_verified=flags&1;dma_long_verified=(flags>>1)&1;ready=1;failed=fail;seen=99;calls=0;spi_divider=2;}
unsigned get(unsigned i){unsigned v[]={dma_verified|(dma_long_verified<<1),ready,seen,calls,spi_divider};return v[i];}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'poll.c').write_text(harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(p/'poll.c'),'-o',str(p/'poll.so')],check=True)
        cls.c=ctypes.CDLL(str(p/'poll.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_polling_and_dma_configuration_restored_after_success_or_failure(self):
        for flags in range(4):
            for failure in range(2):
                with self.subTest(flags=flags,failure=failure):
                    self.c.setup(flags,failure);self.c.tuner_ts_capture_poll()
                    self.assertEqual([self.c.get(i) for i in range(5)],[flags,1-failure,0,1,2])
