import ctypes,importlib.util,pathlib,struct,subprocess,tempfile,unittest,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('host',ROOT/'tools/host.py')
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
class Header(ctypes.BigEndianStructure):
    _fields_=[(n,ctypes.c_uint32) for n in ['magic','version','address','size','crc','entry','reserved','header_crc']]
class Images(unittest.TestCase):
    def image(self,payload=b'hello',**kw):
        values=dict(magic=0x5455564c,version=1,address=0x1c000000,size=len(payload),crc=zlib.crc32(payload),entry=0x1c000000,reserved=0)
        values.update(kw);h=struct.pack('>7I',*values.values())
        return h+struct.pack('>I',zlib.crc32(h))+payload
    def test_actual_images_and_protection(self):
        data=(ROOT/'build/app.img').read_bytes();host.validate_image(data)
        spi=(ROOT/'build/initial-spi.bin').read_bytes()
        self.assertEqual(len(spi),8388608)
        boot=(ROOT/'build/boot.bin').read_bytes()
        self.assertLessEqual(len(boot),8192)
        self.assertEqual(spi[:len(boot)],boot)
        self.assertEqual(spi[len(boot):65536],b'\xff'*(65536-len(boot)))
        self.assertEqual(spi[65536:65536+len(data)],data)
    def test_corruption_truncation_trailing_data(self):
        data=self.image()
        for bad in [data[:-1],data+b'x',b'',bytes(32)]:
            with self.assertRaises(ValueError):host.validate_image(bad)
        for i in range(len(data)):
            bad=bytearray(data);bad[i]^=1
            with self.assertRaises(ValueError):host.validate_image(bad)
    def test_reject_ram_escape(self):
        for kw in [dict(address=0xfff80000),dict(entry=0xfff80000),dict(size=0x100000),dict(size=0),dict(reserved=1),dict(version=2)]:
            with self.assertRaises(ValueError):host.validate_image(self.image(**kw))
    def test_target_c_header_and_crc(self):
        # Execute the target's actual C validator on the host, not a Python copy.
        with tempfile.TemporaryDirectory() as td:
            lib=pathlib.Path(td)/'image.so'
            subprocess.run(['cc','-shared','-fPIC','-Wl,-Bsymbolic','-I'+str(ROOT/'include'),str(ROOT/'src/image.c'),'-o',str(lib)],check=True)
            c=ctypes.CDLL(str(lib));c.crc32.argtypes=[ctypes.c_void_p,ctypes.c_uint32];c.crc32.restype=ctypes.c_uint32
            c.image_valid.argtypes=[ctypes.c_void_p]
            self.assertEqual(c.crc32(b'123456789',9),0xcbf43926)
            c.crc32_update.argtypes=[ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32]
            c.crc32_update.restype=ctypes.c_uint32
            data=bytes(range(256))*3
            state=0xffffffff
            for i in range(0,len(data),64):state=c.crc32_update(state,data[i:i+64],len(data[i:i+64]))
            self.assertEqual(state^0xffffffff,zlib.crc32(data))
            # C consumes SH big-endian values; use native uint32 representation on host.
            for good in [True,False]:
                raw=self.image(address=0x1c000000 if good else 0xfff80000)
                vals=struct.unpack('>8I',raw[:32]);native=(ctypes.c_uint32*8)(*vals)
                native[7]=c.crc32(native,28)
                self.assertEqual(bool(c.image_valid(native)),good)
if __name__=='__main__':unittest.main()
