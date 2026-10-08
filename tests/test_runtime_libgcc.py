"""Reject incompatible compiler runtime objects before publishing an archive."""
import importlib.util
import pathlib
import struct
import tarfile
import io
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runtime_libgcc',ROOT/'tools/runtime_libgcc.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


def header():
    data=bytearray(52);data[:7]=b'\x7fELF\x01\x02\x01'
    struct.pack_into('>HHI',data,16,1,42,1)
    struct.pack_into('>I',data,36,0x13);struct.pack_into('>H',data,40,52)
    return data


class RuntimeObjects(unittest.TestCase):
    def check(self,data):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'runtime.o';path.write_bytes(data)
            return runtime.verify_object(path)

    def test_target_header(self):
        self.assertEqual(self.check(header()),dict(elf_class=32,big_endian=True,machine=42,flags=0x13))

    def test_wrong_endian_class_machine_kind_flags_and_truncation_rejected(self):
        invalid=[b'',header()[:51]]
        for offset,fmt,value in ((4,'B',2),(5,'B',1),(6,'B',0),(16,'>H',2),
            (18,'>H',40),(20,'>I',0),(36,'>I',0x14),(40,'>H',64)):
            data=header();struct.pack_into(fmt,data,offset,value);invalid.append(data)
        for data in invalid:
            with self.assertRaises(ValueError):self.check(data)

    def test_changed_cached_source_is_not_called_unmodified(self):
        with tempfile.TemporaryDirectory() as directory:
            base=pathlib.Path(directory);source=base/'gcc-13.3.0';source.mkdir()
            archive=base/'gcc.tar.xz'
            with tarfile.open(archive,'w:xz') as out:
                entry=tarfile.TarInfo(source.name+'/libgcc.c');entry.size=3
                out.addfile(entry,io.BytesIO(b'abc'))
            (source/'libgcc.c').write_bytes(b'abc')
            self.assertEqual(runtime.verify_source_tree(archive,source),1)
            (source/'libgcc.c').write_bytes(b'abd')
            with self.assertRaises(ValueError):runtime.verify_source_tree(archive,source)


if __name__=='__main__':unittest.main()
