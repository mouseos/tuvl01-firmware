import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class View(ctypes.Structure):
    _fields_=[('frame',ctypes.c_void_p),('length',ctypes.c_uint),
              ('ethertype',ctypes.c_uint16),('station',ctypes.c_uint8),('rcpi',ctypes.c_uint8)]
class Hif(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();lib=pathlib.Path(cls.tmp.name)/'hif.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'include'),str(ROOT/'src/wifi_hif.c'),'-o',str(lib)],check=True)
        cls.c=ctypes.CDLL(str(lib))
        cls.c.wifi_hif_ethernet.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.POINTER(View)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def packet(self,offset=0,ethertype=b'\x08\x00',length=60):
        frame=bytes.fromhex('000369071d226c4ce20d50d4')+ethertype+bytes(length-14)
        n=12+offset+len(frame)
        return n.to_bytes(2,'little')+b'\0\0'+bytes([56|offset,16,0,0,0,100,1,0])+bytes(offset)+frame
    def decode(self,p,network=1):
        view=View(123,123,123,123,123)
        ok=self.c.wifi_hif_ethernet(p,len(p),network,ctypes.byref(view))
        return ok,(ctypes.string_at(view.frame,view.length) if ok else b''),view
    def test_offsets_and_eapol(self):
        for offset in range(4):
            p=self.packet(offset,b'\x88\x8e');ok,frame,v=self.decode(p)
            self.assertEqual(ok,1);self.assertEqual(frame,p[12+offset:])
            self.assertEqual((v.length,v.ethertype,v.station,v.rcpi),(60,0x888e,0,100))
    def test_wrong_format_network_type_and_lengths(self):
        p=self.packet()
        for pos,value in [(0,0),(1,1),(2,1),(2,3),(5,17),(5,32)]:
            bad=bytearray(p);bad[pos]=value
            ok,_,v=self.decode(bytes(bad));self.assertEqual(ok,0)
            self.assertEqual((v.frame,v.length,v.ethertype),(None,0,0))
        for n in range(len(p)):self.assertEqual(self.decode(p[:n])[0],0)
        self.assertEqual(self.decode(p,16)[0],0)
        self.assertEqual(self.decode(self.packet(length=1515))[0],0)
        self.assertEqual(self.decode(self.packet(length=1514))[0],1)
    def test_minimum_header(self):
        for offset in range(4):
            p=self.packet(offset,length=14)
            self.assertEqual(self.decode(p)[0],1)
            bad=p[:-1];bad=len(bad).to_bytes(2,'little')+bad[2:]
            self.assertEqual(self.decode(bad)[0],0)
if __name__=='__main__':unittest.main()
