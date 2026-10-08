import importlib.util,pathlib,struct,subprocess,unittest,zlib

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

if __name__=='__main__':unittest.main()
