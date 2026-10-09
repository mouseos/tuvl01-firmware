"""Exercise the firmware's RTOS yield decision across tick wrap and stalls."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ServiceBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/app.c').read_text()
        start=source.index('static int stream_service_wait(')
        body=source[start:source.index('\nstatic void usb_task',start)]
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'budget.c').write_text('#include <stdint.h>\ntypedef uint32_t TickType_t;\n'
            '#define pdMS_TO_TICKS(x) (x)\n'+body+
            '\nint wait_for_service(uint32_t now,uint32_t start,int progress){'
            'return stream_service_wait(now,start,progress);}\n')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            str(p/'budget.c'),'-o',str(p/'budget.so')],check=True)
        cls.lib=ctypes.CDLL(str(p/'budget.so'))
        cls.wait=cls.lib.wait_for_service
        cls.wait.argtypes=[ctypes.c_uint32,ctypes.c_uint32,ctypes.c_int]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_progress_yields_at_four_ticks_including_counter_wrap(self):
        for start in [0,100,0xfffffffe]:
            for elapsed in range(8):
                self.assertEqual(self.wait((start+elapsed)&0xffffffff,start,1),int(elapsed>=4))
    def test_stall_or_inactive_always_yields(self):
        for start,now in [(0,0),(100,101),(0xfffffffe,1)]:
            self.assertEqual(self.wait(now,start,0),1)
if __name__=='__main__':unittest.main()
