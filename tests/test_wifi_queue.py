import ctypes,pathlib,struct,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class Queues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        library=pathlib.Path(cls.tmp.name)/'queues.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
                        '-I'+str(ROOT/'include'),str(ROOT/'src/wifi_queue.c'),
                        '-o',str(library)],check=True)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.wifi_queue_pack.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
        cls.lib.wifi_queue_pack.restype=ctypes.c_uint
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_profiles_wire_bytes_and_sentinels(self):
        public=((15,127,0,3),(15,1023,0,7),(7,15,94,1),(3,7,47,1))
        stock=((7,15,94,1),(15,1023,0,7),(7,15,94,1),(1,7,47,1))
        for mode in range(3):
            output=(ctypes.c_uint8*60)(*([0xa5]*60))
            self.assertEqual(self.lib.wifi_queue_pack(output,60,mode),52)
            expected=b'\0'*8+b''.join(struct.pack('>4H' if mode==2 else '<4H',*ac)+b'\0\0'
                                      for ac in (public if mode==0 else stock))+b'\1\0\0\0'
            self.assertEqual(bytes(output[:52]),expected)
            self.assertEqual(bytes(output[52:]),b'\xa5'*8)
    def test_reject_invalid_capacity_mode_and_null_without_writing(self):
        for capacity,mode in ((0,0),(51,0),(52,3),(52,0xffffffff)):
            output=(ctypes.c_uint8*60)(*([0xa5]*60))
            self.assertEqual(self.lib.wifi_queue_pack(output,capacity,mode),0)
            self.assertEqual(bytes(output),b'\xa5'*60)
        self.assertEqual(self.lib.wifi_queue_pack(None,52,0),0)

if __name__=='__main__':unittest.main()
