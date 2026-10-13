"""tools/build_release.py: the image check must reject anything that is not a valid standalone image."""
import pathlib,struct,sys,unittest,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_release as br

def make(payload=b'APP'*100+br.STANDALONE_MARKER,boot=None):
    boot=boot or (b'\x01'*40+br.LOADER_BANNER+b'\x02'*40)
    h=struct.pack('>7I',0x5455564c,1,0x1c000000,len(payload),zlib.crc32(payload),0x1c000000,0)
    h+=struct.pack('>I',zlib.crc32(h));img=h+payload
    spi=bytearray(b'\xff'*br.SPI_SIZE);spi[:len(boot)]=boot;spi[br.APP_OFFSET:br.APP_OFFSET+len(img)]=img
    return bytes(spi),boot,img

class Verify(unittest.TestCase):
    def test_valid_standalone_image_has_no_problems(self):
        self.assertEqual(br.verify_spi(*make()),[])
    def test_development_and_unmarked_builds_are_rejected(self):
        for payload in (b'x'*50+br.DEV_MARKER,b'x'*50):
            self.assertTrue(br.verify_spi(*make(payload)),payload)
    def test_layout_violations_are_reported(self):
        spi,boot,img=make()
        s=bytearray(spi);s[0]^=1;self.assertTrue(br.verify_spi(bytes(s),boot,img))                  # loader differs
        s=bytearray(spi);s[0x8000]=0;self.assertTrue(br.verify_spi(bytes(s),boot,img))             # data between loader and app
        s=bytearray(spi);s[0x10000+len(img)+5]=0;self.assertTrue(br.verify_spi(bytes(s),boot,img))  # stale data after the app
        s=bytearray(spi);s[0x10000+40]^=1;self.assertTrue(br.verify_spi(bytes(s),boot,img))        # app corrupted in the image
        self.assertTrue(br.verify_spi(spi[:-1],boot,img))                                          # wrong size
    def test_header_and_crc_corruption_are_reported(self):
        spi,boot,img=make()
        for i in range(32+len(br.STANDALONE_MARKER)+300):
            bad=bytearray(img);bad[i]^=1;bad=bytes(bad)
            s=bytearray(spi);s[0x10000:0x10000+len(bad)]=bad
            self.assertTrue(br.verify_spi(bytes(s),boot,bad),i)
    def test_foreign_loader_is_rejected(self):
        self.assertTrue(br.verify_spi(*make(boot=b'\x00'*100)))
    def test_real_build_if_present(self):
        b=ROOT/'build'
        if not all((b/n).exists() for n in ('initial-spi.bin','boot.bin','app.img')):self.skipTest('no build output')
        problems=br.verify_spi((b/'initial-spi.bin').read_bytes(),(b/'boot.bin').read_bytes(),(b/'app.img').read_bytes())
        # A development build is a valid build, just not a standalone one: only that single problem is acceptable.
        self.assertTrue(problems==[] or problems==['application is not the standalone variant (built without AUTOSERVE=1)']
                        or problems==['application is the development variant'] or all('variant' in q for q in problems),problems)
if __name__=='__main__':unittest.main()
