"""tools/extract_vendor.py: accepts only a matching dump, never guesses."""
import hashlib,os,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import extract_vendor as ev
def synthetic():
    blobs={'a.bin':bytes(range(256))*4,'b.bin':b'\x5a'*300}
    dump=bytearray(b'\xff'*ev.DUMP_SIZE);table={};pos=0x2000
    for name,data in blobs.items():
        dump[pos:pos+len(data)]=data;table[name]=(pos,len(data),hashlib.sha256(data).hexdigest());pos+=0x1000
    return bytes(dump),table,blobs
class Extract(unittest.TestCase):
    def test_extracts_exact_bytes(self):
        dump,table,blobs=synthetic();self.assertEqual(ev.extract(dump,table),blobs)
    def test_refuses_wrong_size_and_changed_data(self):
        dump,table,_=synthetic()
        with self.assertRaises(ValueError):ev.extract(dump[:-1],table)
        bad=bytearray(dump);bad[0x2000]^=1
        with self.assertRaises(ValueError):ev.extract(bytes(bad),table)
    def test_real_table_matches_the_repository_blobs_when_present(self):
        # The hashes in the table must be the ones the build verifies.
        for name,(offset,size,sha) in ev.BLOCKS.items():
            blob=ROOT/'firmware'/name
            if blob.exists():
                data=blob.read_bytes();self.assertEqual((len(data),hashlib.sha256(data).hexdigest()),(size,sha))
    def test_command_line_writes_files_and_reports_mismatch(self):
        dump,table,blobs=synthetic()
        with tempfile.TemporaryDirectory() as t:
            t=pathlib.Path(t);(t/'d.bin').write_bytes(dump)
            old=ev.BLOCKS;ev.BLOCKS=table
            try:
                self.assertEqual(ev.main([str(t/'d.bin'),'--out',str(t/'o')]),0)
                for name,data in blobs.items():self.assertEqual((t/'o'/name).read_bytes(),data)
                (t/'x.bin').write_bytes(b'\xff'*ev.DUMP_SIZE)
                self.assertEqual(ev.main([str(t/'x.bin'),'--out',str(t/'o2')]),1);self.assertFalse((t/'o2').exists())
            finally:ev.BLOCKS=old
if __name__=='__main__':unittest.main()
