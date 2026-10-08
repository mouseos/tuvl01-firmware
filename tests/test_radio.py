import ctypes,importlib.util,pathlib,struct,subprocess,tempfile,unittest,zlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('verify_radio',ROOT/'tools/verify_radio.py')
radio_check=importlib.util.module_from_spec(spec);spec.loader.exec_module(radio_check)

def radio_offsets():
    symbols={}
    for line in subprocess.check_output(['sh-elf-nm',str(ROOT/'build/app.elf')],text=True).splitlines():
        parts=line.split()
        if len(parts)==3:symbols[parts[2]]=int(parts[0],16)
    return tuple(symbols[name]-0x1c000000 for name in
                 ('_wifi_radio_descriptor','_wifi_radio_bytes','_wifi_radio_end'))

class Radio(unittest.TestCase):
    def test_bundled_dependency_and_target_layout(self):
        radio=(ROOT/'firmware/mt5931.bin').read_bytes()
        radio_check.verify(radio)
        payload=(ROOT/'build/app.bin').read_bytes()
        descriptor,start,end=radio_offsets()
        self.assertEqual(descriptor%16,0)
        self.assertEqual(start,descriptor+16)
        self.assertEqual(end,start+len(radio))
        self.assertEqual(end,len(payload))
        self.assertEqual(struct.unpack_from('>4I',payload,descriptor),
                         (0x4d543331,len(radio),zlib.crc32(radio),0xff900000))
        self.assertEqual(payload[start:end],radio)

    def test_reject_changed_or_missing_radio(self):
        radio=(ROOT/'firmware/mt5931.bin').read_bytes()
        corrupt=bytearray(radio);corrupt[len(corrupt)//2]^=1
        for data in (b'',radio[:-1],corrupt):
            with self.assertRaises(ValueError):radio_check.verify(data)

    def test_target_descriptor_length_and_crc_guards(self):
        source=(ROOT/'src/sdio.c').read_text()
        actual=source[source.index('static int radio_image_valid(void){'):source.index('static int radio_boot(unsigned force){')]
        harness=r"""
#include <stdint.h>
#include <stddef.h>
static uint8_t storage[262208];
static const uint8_t *wifi_radio_bytes=storage,*wifi_radio_end;
static uint32_t wifi_radio_descriptor[4];
static uint32_t crc32(const uint8_t *p,unsigned n){
 uint32_t c=~0U;while(n--){c^=*p++;for(unsigned i=0;i<8;i++)c=(c>>1)^((0U-(c&1U))&0xedb88320U);}return ~c;
}
"""
        wrapper=r"""
int check(unsigned length,unsigned actual_length,unsigned fault){
 wifi_radio_end=storage+actual_length;
 wifi_radio_descriptor[0]=0x4d543331;wifi_radio_descriptor[1]=length;
 wifi_radio_descriptor[2]=crc32(storage,actual_length);wifi_radio_descriptor[3]=0xff900000U;
 if(fault==1)wifi_radio_descriptor[0]^=1;
 if(fault==2)wifi_radio_descriptor[2]^=1;
 if(fault==3)wifi_radio_descriptor[3]^=1;
 return radio_image_valid();
}
"""
        with tempfile.TemporaryDirectory() as folder:
            c=pathlib.Path(folder)/'guard.c';library=pathlib.Path(folder)/'guard.so'
            c.write_text(harness+actual+wrapper)
            subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(c),'-o',str(library)],check=True)
            probe=ctypes.CDLL(str(library))
            for length in (64,136576,139776,262144):
                self.assertEqual(probe.check(length,length,0),1)
                for fault in (1,2,3):self.assertEqual(probe.check(length,length,fault),0)
            for length,actual_length in ((0,0),(65,65),(262208,262208),(139776,136576)):
                self.assertEqual(probe.check(length,actual_length,0),0)

    def test_external_selection_hash_guard_and_stable_config(self):
        radio=(ROOT/'firmware/mt5931.bin').read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            source=pathlib.Path(folder)/'radio.bin';source.write_bytes(radio)
            config=pathlib.Path(folder)/'config.h'
            radio_check.configure(source,config)
            self.assertIn('#define RADIO_LENGTH 136576',config.read_text())
            self.assertIn('#define RADIO_CRC 0x1061bd8e',config.read_text())
            before=config.stat().st_mtime_ns
            radio_check.configure(source,config)
            self.assertEqual(config.stat().st_mtime_ns,before)
            for expected in (radio_check.CANDIDATE_SHA,'0'*64):
                with self.assertRaises(ValueError):radio_check.configure(source,config,expected)
            self.assertEqual(config.stat().st_mtime_ns,before)

if __name__=='__main__':unittest.main()
