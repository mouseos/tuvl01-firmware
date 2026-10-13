"""Extract the two data blocks the firmware build needs (MT5931 radio firmware, MN885521 patch
records) from a stock SPI dump of the unit.

usage: python tools/extract_vendor.py STOCK_DUMP.BIN [--out firmware]

Each block is located at the offset it has in the stock firmware image and accepted only when its
SHA-256 matches the hash the build verifies (tools/verify_radio.py, tools/pseq.py). A dump of another
stock firmware version is refused instead of guessed.
"""
import argparse,hashlib,pathlib,sys

# name -> (offset in the stock 8 MiB SPI dump, size, sha256)
BLOCKS={
    'mt5931.bin':(0x103650,136576,'06d43badbb669700c7cf94924c43a40779b428f3ceec8756813b0aaec2b4a68d'),
    'mn885521-pseq.bin':(0xffe94,4341,'fb67866165fedb7eceea6a4f26fc797314f2ef8f3a7d1f7bb730dc6ecc651751'),
}
DUMP_SIZE=8*1024*1024

def extract(dump,blocks=None):
    """Returns {name: bytes}. Raises ValueError with a reason when the dump does not match."""
    if blocks is None:blocks=BLOCKS
    if len(dump)!=DUMP_SIZE:
        raise ValueError('expected an 8388608-byte dump of the S25FL164K, got %d bytes'%len(dump))
    found={}
    for name,(offset,size,sha) in blocks.items():
        data=dump[offset:offset+size]
        if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:
            raise ValueError('%s: data at 0x%x does not match the expected SHA-256 '
                             '(a different stock firmware version?)'%(name,offset))
        found[name]=data
    return found

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('dump',type=pathlib.Path)
    p.add_argument('--out',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1]/'firmware')
    a=p.parse_args(argv)
    try:blocks=extract(a.dump.read_bytes())
    except (OSError,ValueError) as e:
        print('ERROR:',e,file=sys.stderr);return 1
    a.out.mkdir(parents=True,exist_ok=True)
    for name,data in blocks.items():
        (a.out/name).write_bytes(data);print('wrote',a.out/name,len(data),'bytes sha256 verified')
    return 0
if __name__=='__main__':raise SystemExit(main())
