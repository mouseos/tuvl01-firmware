"""Unmodified GCC 13.3.0, C only; run under Linux/WSL."""
import argparse, hashlib, os, pathlib, shutil, subprocess, tarfile, urllib.request
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rsn-runtime',action='store_true',
                    help='Also build the selected SH-2A integer libgcc runtime from source')
args=parser.parse_args()
root = pathlib.Path(__file__).resolve().parents[1]
base = pathlib.Path(os.environ.get('TUVL_TOOLCHAIN_DIR', str(pathlib.Path.home() / '.cache/tuvl01-independent/gcc13')))
base.mkdir(parents=True, exist_ok=True)
archive = base / 'gcc-13.3.0.tar.xz'
cached = pathlib.Path.home() / '.cache/tuvl01/toolchain/gcc-13.3.0.tar.xz'
if not archive.exists():
    if cached.exists():
        shutil.copyfile(cached, archive)
    else:
        urllib.request.urlretrieve('https://ftp.gnu.org/gnu/gcc/gcc-13.3.0/gcc-13.3.0.tar.xz', archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == '0845e9621c9543a13f484e94584a49ffc0129970e9914624235fc1d061a0c083'
source = base / 'gcc-13.3.0'
if not source.exists():
    with tarfile.open(archive) as tf:
        tf.extractall(base, filter='data')
build = base / 'gcc-build'
build.mkdir(exist_ok=True)
def run(args):
    subprocess.run(args, cwd=build, check=True)
if not (build / 'Makefile').exists():
    run([str(source / 'configure'), '--target=sh-elf', '--with-cpu=sh2a', '--with-endian=big',
         '--prefix=' + str(base / 'install'), '--enable-languages=c',
         '--without-headers', '--disable-bootstrap', '--disable-multilib',
         '--disable-libssp', '--disable-libquadmath', '--disable-libatomic',
         '--disable-libgomp', '--disable-libsanitizer', '--disable-nls', '--disable-werror',
         '--with-as=/usr/bin/sh-elf-as', '--with-ld=/usr/bin/sh-elf-ld'])
run(['make', '-j' + str(min(os.cpu_count() or 2, 8)), 'all-gcc'])
run(['make', 'install-gcc'])
if args.rsn_runtime:
    from runtime_libgcc import build_runtime
    build_runtime(base)
