"""Verify every byte of a TS DMA loopback capture; no broadcast is required."""
import argparse,pathlib,sys

def expected_byte(offset):
    packet,i=divmod(offset%6016,188)
    if i<4:return (0x47,0x1f,0xfe,0x10|(packet&15))[i]
    return (i*37+packet*11+3)&255

def verify(data):
    if not data or len(data)%188:raise ValueError('Capture must contain complete TS packets')
    errors=0;first=None
    for n,b in enumerate(data):
        if b!=expected_byte(n):
            if first is None:first=n
            errors+=1
    return dict(bytes=len(data),packets=len(data)//188,errors=errors,first_offset=first)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture');a=p.parse_args()
    try:result=verify(pathlib.Path(a.capture).read_bytes())
    except ValueError as e:p.error(str(e))
    print(result);return bool(result['errors'])
if __name__=='__main__':sys.exit(main())
