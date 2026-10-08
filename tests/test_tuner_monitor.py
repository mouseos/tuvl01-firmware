import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class FrameState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        library=pathlib.Path(cls.tmp.name)/'monitor.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(ROOT/'src/tuner_monitor_protocol.c'),'-o',str(library)],check=True)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.tuner_frame_state.argtypes=[ctypes.c_uint8,ctypes.c_uint8]
        cls.lib.tuner_frame_state.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_completion_and_other_sync_flags_are_not_frame_lock(self):
        for stage in (0,1,3,10,15):
            for flags in (0,1,2,4,32,128):self.assertEqual(self.lib.tuner_frame_state(stage,flags),0)
    def test_frame_lock_can_coexist_with_partial_flag(self):
        for flags in (16,20,48,52):self.assertEqual(self.lib.tuner_frame_state(10,flags),1)
    def test_error_flags_override_apparent_frame_lock(self):
        for stage,flags in ((0,24),(128,16),(255,255),(240,16)):
            self.assertEqual(self.lib.tuner_frame_state(stage,flags),-1)
