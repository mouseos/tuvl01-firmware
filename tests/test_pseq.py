import importlib.util,json,pathlib,unittest
from test_radio import radio_offsets

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pseq',ROOT/'tools/pseq.py')
pseq=importlib.util.module_from_spec(spec);spec.loader.exec_module(pseq)

class Pseq(unittest.TestCase):
    def setUp(self):
        self.data=(ROOT/'firmware/mn885521-pseq.bin').read_bytes()
        self.manifest=(ROOT/'firmware/mn885521-pseq.json').read_bytes()
    def test_integrity_and_linked_asset(self):
        records=pseq.verify(self.data,self.manifest)
        self.assertEqual(sum(r['payload_size'] for r in records),4251)
        self.assertIn(self.data,(ROOT/'build/app.bin').read_bytes()[:radio_offsets()[0]])
    def test_changed_truncated_or_missing_asset(self):
        changed=bytearray(self.data);changed[120]^=1
        for data in (b'',self.data[:-1],changed,self.data+b'\0'):
            with self.assertRaises(ValueError):pseq.verify(data,self.manifest)
    def test_manifest_line_endings_preserve_integrity(self):
        self.assertEqual(pseq.verify(self.data,self.manifest),
                         pseq.verify(self.data,self.manifest.replace(b'\n',b'\r\n')))
    def test_reject_wrong_target_or_record_boundary(self):
        for field,value in (('bank',0x62),('offset',1),('payload_size',9999)):
            meta=json.loads(self.manifest);meta['records'][0][field]=value
            with self.assertRaises(ValueError):pseq.verify(self.data,json.dumps(meta).encode())

if __name__=='__main__':unittest.main()
