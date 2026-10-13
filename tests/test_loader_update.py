"""Loader rewrite: image validation, protection refusal, ordering and failure behaviour."""
import ctypes,pathlib,subprocess,tempfile,unittest,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
BANNER=b'TUVL01 independent recovery boot'
MOCK=r'''
#include <stdint.h>
#include <string.h>
#define N 0x20000
static uint8_t nor[N];
static int jedec=0x014017,sr=0,fail_erase_at=-1,fail_program_at=-1,erases,programs;
static uint32_t erased[8];
uint32_t flash_id(void){return jedec;}
int flash_status(void){return sr;}
int flash_read(uint32_t a,void*d,uint32_t n){memcpy(d,nor+a,n);return 0;}
int flash_boot_erase(uint32_t a){
  if(a==(uint32_t)fail_erase_at)return -1;
  memset(nor+a,0xff,4096);erased[erases++]=a;return 0;}
int flash_boot_program(uint32_t a,const void*d,uint32_t n){
  if(a==(uint32_t)fail_program_at)return -1;
  for(uint32_t i=0;i<n;i++){nor[a+i]&=((const uint8_t*)d)[i];}
  programs++;return 0;}
uint32_t crc32(const void*d,uint32_t n){
  const uint8_t*p=d;uint32_t c=0xffffffffu;
  while(n--){c^=*p++;for(int b=0;b<8;b++)c=(c>>1)^((0-(c&1))&0xedb88320u);}return ~c;}
void setup(const uint8_t*old,int id,int status,int fe,int fp){
  memcpy(nor,old,8192);jedec=id;sr=status;fail_erase_at=fe;fail_program_at=fp;erases=programs=0;}
uint8_t*memory(void){return nor;}
unsigned metric(unsigned i){unsigned m[]={erases,programs,erased[0],erased[1]};return m[i];}
'''
class Loader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'mock.c').write_text(MOCK)
        (p/'board.h').write_text('#include <stdint.h>\nint flash_read(uint32_t,void*,uint32_t);')
        (p/'image.h').write_text('#include "board.h"\nuint32_t crc32(const void*,uint32_t);uint32_t flash_id(void);int flash_status(void);int flash_boot_erase(uint32_t);int flash_boot_program(uint32_t,const void*,uint32_t);')
        # Python already has zlib's crc32 loaded; keep the firmware symbol from being interposed.
        subprocess.run(['cc','-shared','-fPIC','-Dcrc32=fw_crc32','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'include'),
            str(ROOT/'src/loader_update.c'),str(p/'mock.c'),'-o',str(p/'lu.so')],check=True)
        c=cls.c=ctypes.CDLL(str(p/'lu.so'))
        c.loader_image_check.argtypes=[ctypes.c_char_p,ctypes.c_uint32]
        c.loader_update_apply.argtypes=[ctypes.c_char_p]
        c.setup.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int]
        c.memory.restype=ctypes.POINTER(ctypes.c_uint8);c.metric.restype=ctypes.c_uint
        c.metric.argtypes=[ctypes.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def image(self,fill=0x11):
        body=bytearray(b'\xff'*8192);body[100:100+len(BANNER)]=BANNER
        body[0:64]=bytes([fill])*64;body[4096:4096+300]=bytes([fill^0x22])*300  # page 0 and part of sector 1 are non-blank
        return bytes(body)
    def old(self):return bytes([0x5a])*8192
    def mem(self):return bytes(self.c.memory()[i] for i in range(8192))
    def test_check_accepts_valid_and_rejects_bad_crc_and_foreign_images(self):
        img=self.image();crc=zlib.crc32(img)&0xffffffff
        self.assertEqual(self.c.loader_image_check(img,crc),0)
        self.assertEqual(self.c.loader_image_check(img,crc^1),-1)
        foreign=b'\x00'*8192;self.assertEqual(self.c.loader_image_check(foreign,zlib.crc32(foreign)&0xffffffff),-2)
        truncated=bytearray(img);truncated[100+10]=0
        self.assertEqual(self.c.loader_image_check(bytes(truncated),zlib.crc32(bytes(truncated))&0xffffffff),-2)
    def test_success_writes_sector1_before_sector0_and_equals_image(self):
        img=self.image();self.c.setup(self.old(),0x014017,0,-1,-1)
        self.assertEqual(self.c.loader_update_apply(img),0)
        self.assertEqual(self.mem(),img);self.assertEqual(self.c.metric(0),2)
        self.assertEqual((self.c.metric(2),self.c.metric(3)),(0x1000,0))   # order of erases
        self.assertLess(self.c.metric(1),32)                                  # blank pages are skipped
    def test_wrong_flash_or_block_protection_touch_nothing(self):
        img=self.image()
        for ident,status,expect in ((0x014018,0,-3),(0x014017,0x04,-4),(0x014017,0x20,-4),(0x014017,0x40,-4)):
            self.c.setup(self.old(),ident,status,-1,-1)
            self.assertEqual(self.c.loader_update_apply(img),expect);self.assertEqual(self.c.metric(0),0)
            self.assertEqual(self.mem(),self.old())
    def test_failure_in_sector1_leaves_sector0_loader_untouched(self):
        img=self.image()
        for fe,fp,expect in ((0x1000,-1,-5),(-1,0x1000,-6)):
            self.c.setup(self.old(),0x014017,0,fe,fp)
            self.assertEqual(self.c.loader_update_apply(img),expect)
            self.assertEqual(self.mem()[:4096],self.old()[:4096])
    def test_verify_catches_a_program_that_silently_did_nothing(self):
        # a NOR that ignores programming (e.g. hidden protection) must be reported, not accepted
        img=self.image();self.c.setup(self.old(),0x014017,0,-1,0x1000)
        self.assertNotEqual(self.c.loader_update_apply(img),0)
if __name__=='__main__':unittest.main()
