"""Build selected integer GCC runtime from the configured, pinned compiler source.

Run under Linux/WSL after bootstrap.py. No precompiled runtime is imported.
This does not build the floating-point or hosted C/unwind runtime.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import tarfile

SOURCE_SHA256='0845e9621c9543a13f484e94584a49ffc0129970e9914624235fc1d061a0c083'
OBJECTS=('_ashldi3','_lshrdi3','_divdi3','_udivdi3','_umoddi3',
         '_udivmoddi4','_clzsi2','_clz','_movmem','_udiv_qrnnd_16')


def sha256(path):
    with pathlib.Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_object(path):
    with pathlib.Path(path).open('rb') as stream:
        header=stream.read(52)
    if len(header)!=52 or header[:7]!=b'\x7fELF\x01\x02\x01':
        raise ValueError('Runtime object must be ELF32 big endian version 1')
    kind,machine,version=struct.unpack_from('>HHI',header,16)
    flags=struct.unpack_from('>I',header,36)[0]
    size=struct.unpack_from('>H',header,40)[0]
    if (kind,machine,version,flags,size)!=(1,42,1,0x13,52):
        raise ValueError('Runtime object must target SH-2A no-FPU relocatable ELF')
    return dict(elf_class=32,big_endian=True,machine=42,flags=flags)


def verify_source_tree(archive,source):
    source=pathlib.Path(source).resolve();count=0
    with tarfile.open(archive,'r|xz') as contents:
        for member in contents:
            relative=pathlib.PurePosixPath(member.name)
            if relative.parts[0]!=source.name or '..' in relative.parts:
                raise ValueError('Unexpected GCC archive source path')
            path=source.joinpath(*relative.parts[1:])
            if member.issym():
                if not path.is_symlink() or os.readlink(path)!=member.linkname:
                    raise ValueError('Cached GCC source symlink differs from archive')
                continue
            if not member.isfile():continue
            if path.is_symlink() or not path.resolve().is_relative_to(source):
                raise ValueError('Cached GCC source escapes the source tree')
            stream=contents.extractfile(member)
            expected=hashlib.file_digest(stream,'sha256').hexdigest()
            if sha256(path)!=expected:
                raise ValueError('Cached GCC source differs from pinned archive')
            count+=1
    if not count:raise ValueError('GCC source archive contains no source files')
    return count


def build_runtime(base):
    base=pathlib.Path(base).resolve()
    source=base/'gcc-13.3.0'
    build=base/'gcc-build'
    install=base/'install'
    if not (build/'Makefile').is_file() or not (install/'bin/sh-elf-gcc').is_file():
        raise ValueError('Run tools/bootstrap.py first to configure/build GCC')
    if sha256(base/'gcc-13.3.0.tar.xz')!=SOURCE_SHA256:
        raise ValueError('Pinned GCC source archive hash mismatch')
    if not (source/'libgcc/libgcc2.c').is_file():
        raise ValueError('Pinned GCC source tree is missing')
    verified_sources=verify_source_tree(base/'gcc-13.3.0.tar.xz',source)
    subprocess.run(['make','-C',str(build),'configure-target-libgcc',
                    'CFLAGS_FOR_TARGET=-O2 -m2a-nofpu -mb -ffreestanding'],check=True)
    runtime_build=(build/'sh-elf/libgcc').resolve()
    if not runtime_build.is_relative_to(build) or not (runtime_build/'Makefile').is_file():
        raise ValueError('Configured runtime build must stay inside GCC build tree')
    outputs=[]
    for name in OBJECTS:
        path=runtime_build/(name+'.o')
        # Rebuild these ten generated objects even if an earlier configuration
        # left cached outputs with different target flags. Never remove sources.
        if path.is_symlink() or path.resolve().parent!=runtime_build:
            raise ValueError('Unexpected runtime output path')
        if path.exists():path.unlink()
        outputs.append(path)
    subprocess.run(['make','-C',str(runtime_build),'-j4',
                    'CFLAGS=-O2 -m2a-nofpu -mb -ffreestanding',
                    *[path.name for path in outputs]],check=True)
    facts={path.name:dict(sha256=sha256(path),**verify_object(path)) for path in outputs}
    destination=install/'lib/tuvl01'
    destination.mkdir(parents=True,exist_ok=True)
    archive=destination/'libgcc-sh2a-be.a'
    temporary=destination/'libgcc-sh2a-be.a.tmp'
    # GNU ar deterministic mode removes build-time metadata from the archive.
    if temporary.exists():temporary.unlink()
    subprocess.run(['sh-elf-ar','rcsD',str(temporary),*[str(path) for path in outputs]],check=True)
    temporary.replace(archive)
    notices=install/'share/licenses/gcc13-runtime'
    notices.mkdir(parents=True,exist_ok=True)
    for name in ('COPYING3','COPYING.RUNTIME'):
        shutil.copyfile(source/name,notices/name)
    metadata=dict(source_url='https://ftp.gnu.org/gnu/gcc/gcc-13.3.0/gcc-13.3.0.tar.xz',
                  source_sha256=SOURCE_SHA256,target='SH-2A big endian no FPU',
                  cflags='-O2 -m2a-nofpu -mb -ffreestanding',objects=facts,
                  archive_sha256=sha256(archive),source_modified=False,
                  source_files_verified=verified_sources,
                  hardware_executed=False)
    (destination/'libgcc-sh2a-be.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    return archive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-dir',type=pathlib.Path,default=os.environ.get(
        'TUVL_TOOLCHAIN_DIR',str(pathlib.Path.home()/'.cache/tuvl01-independent/gcc13')))
    args=parser.parse_args()
    print('Source-built integer runtime:',build_runtime(args.toolchain_dir))


if __name__=='__main__':
    main()
