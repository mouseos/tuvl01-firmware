"""Build the SPI image for a standalone TUVL01 receiver from the owner's own stock dump.

usage: python tools/build_release.py STOCK_DUMP.BIN [--out release] [--no-build]

1. checks the dump and extracts the two manufacturer data blocks (tools/extract_vendor.py; they are
   not part of a public release, every unit carries them in its SPI NOR);
2. builds the standalone variant (make AUTOSERVE=1; on Windows through WSL);
3. checks the result (layout, CRC, standalone marker) and writes the 8 MiB image to program into the
   S25FL164K, a checksum file and the BonDriver if it has been built.

The output contains the manufacturer's radio firmware. Keep it for your own unit; do not publish it.
"""
import argparse,hashlib,json,os,pathlib,shutil,struct,subprocess,sys,zlib
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
import extract_vendor

SPI_SIZE=8*1024*1024
APP_OFFSET=0x10000
LOADER_SIZE=8192
APP_LIMIT=0xfc000
STANDALONE_MARKER=b'Build variant=standalone'
DEV_MARKER=b'Build variant=development'
LOADER_BANNER=b'TUVL01 independent recovery boot'

def verify_spi(spi,boot,app_img):
    """Returns a list of problems (empty when the image is a valid standalone image)."""
    problems=[]
    if len(spi)!=SPI_SIZE:problems.append('image is %d bytes, expected %d'%(len(spi),SPI_SIZE))
    if not 0<len(boot)<=LOADER_SIZE or LOADER_BANNER not in boot:problems.append('loader is not a valid loader image')
    if spi[:len(boot)]!=boot:problems.append('loader is not at offset 0')
    if spi[len(boot):APP_OFFSET].strip(b'\xff'):problems.append('area between loader and application is not blank')
    if len(app_img)<32:
        problems.append('application image too short');return problems
    magic,version,address,size,crc,entry,reserved,header_crc=struct.unpack('>8I',app_img[:32])
    if (magic,version,address,entry,reserved)!=(0x5455564c,1,0x1c000000,0x1c000000,0):problems.append('application header fields are wrong')
    if zlib.crc32(app_img[:28])!=header_crc:problems.append('application header CRC is wrong')
    if not 0<size<=APP_LIMIT or len(app_img)!=32+size:problems.append('application size is inconsistent')
    elif zlib.crc32(app_img[32:])!=crc:problems.append('application payload CRC is wrong')
    if spi[APP_OFFSET:APP_OFFSET+len(app_img)]!=app_img:problems.append('application is not at 0x10000')
    if spi[APP_OFFSET+len(app_img):].strip(b'\xff'):problems.append('data after the application is not blank')
    if STANDALONE_MARKER not in app_img:problems.append('application is not the standalone variant (built without AUTOSERVE=1)')
    if DEV_MARKER in app_img:problems.append('application is the development variant')
    return problems

def run_make(clean):
    for name in clean:
        p=ROOT/'build'/name
        if p.exists():p.unlink()
    if os.name=='nt':
        cmd=['wsl','bash','-lc','cd "$(wslpath -a \'%s\')" && make AUTOSERVE=1'%ROOT]
    else:
        cmd=['make','AUTOSERVE=1'];
    return subprocess.run(cmd,cwd=ROOT).returncode

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('dump',type=pathlib.Path,nargs='?',help='stock SPI dump; omit to use the data in firmware/')
    p.add_argument('--out',type=pathlib.Path,default=ROOT/'release')
    p.add_argument('--no-build',action='store_true',help='package the existing build/ (still verified)')
    a=p.parse_args(argv)
    fw=ROOT/'firmware'
    if a.dump is not None:
        try:blocks=extract_vendor.extract(a.dump.read_bytes())
        except (OSError,ValueError) as e:
            print('ERROR:',e,file=sys.stderr);return 1
        for name,data in blocks.items():
            target=fw/name
            if not target.exists() or target.read_bytes()!=data:
                fw.mkdir(exist_ok=True);target.write_bytes(data);print('wrote',target)
    else:
        # No dump: use the manufacturer data that ships in firmware/, but only if it is exactly the expected one.
        for name,(offset,size,sha) in extract_vendor.BLOCKS.items():
            try:data=(fw/name).read_bytes()
            except OSError as e:print('ERROR: %s missing (%s); pass a stock dump to extract it'%(name,e),file=sys.stderr);return 1
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:
                print('ERROR: firmware/%s does not match the expected SHA-256'%name,file=sys.stderr);return 1
    if not a.no_build:
        rc=run_make(['app.elf','app.bin','app.img','initial-spi.bin','boot.bin','boot.elf','manifest.json'])
        if rc:print('ERROR: build failed (%d)'%rc,file=sys.stderr);return 2
    b=ROOT/'build'
    try:spi=(b/'initial-spi.bin').read_bytes();boot=(b/'boot.bin').read_bytes();img=(b/'app.img').read_bytes()
    except OSError as e:
        print('ERROR: build output missing:',e,file=sys.stderr);return 2
    problems=verify_spi(spi,boot,img)
    if problems:
        for q in problems:print('ERROR:',q,file=sys.stderr)
        return 3
    out=a.out;out.mkdir(parents=True,exist_ok=True)
    (out/'tuvl01-spi-8MiB.bin').write_bytes(spi)
    sums={'tuvl01-spi-8MiB.bin':hashlib.sha256(spi).hexdigest()}
    if a.dump is not None:sums['stock-dump-input']=hashlib.sha256(a.dump.read_bytes()).hexdigest()
    dll=ROOT/'client'/'bondriver'/'build'/'BonDriver_TUVL01.dll'
    if dll.exists():
        shutil.copy2(dll,out/dll.name);sums[dll.name]=hashlib.sha256(dll.read_bytes()).hexdigest()
    (out/'SHA256SUMS.txt').write_text(''.join('%s  %s\n'%(v,k) for k,v in sums.items()),encoding='utf-8')
    print('OK: wrote',out/'tuvl01-spi-8MiB.bin',len(spi),'bytes');print(json.dumps(sums,indent=2))
    print('Next: read out and keep the unit\'s own SPI first (twice, compare), then program this image into the S25FL164K and verify it by reading it back.')
    return 0
if __name__=='__main__':raise SystemExit(main())
