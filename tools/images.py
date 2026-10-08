"""Package independent MCU firmware with its bundled MT5931 radio dependency."""
import hashlib,json,pathlib,struct,zlib
root=pathlib.Path(__file__).resolve().parents[1]
b=root/'build'
payload=(b/'app.bin').read_bytes()
boot=(b/'boot.bin').read_bytes()
assert 0<len(boot)<=8192
assert 0<len(payload)<=0xfc000
h=struct.pack('>7I',0x5455564c,1,0x1c000000,len(payload),zlib.crc32(payload),0x1c000000,0)
h+=struct.pack('>I',zlib.crc32(h))
(b/'app.img').write_bytes(h+payload)
spi=bytearray(b'\xff'*8388608)
spi[:len(boot)]=boot
spi[0x10000:0x10000+len(h)+len(payload)]=h+payload
(b/'initial-spi.bin').write_bytes(spi)
meta={'hardware_tested':False,'application_address':'0x1c000000','application_flash_offset':'0x10000','protected_flash_range':'[0x0,0x10000)', 'files':{}}
for name in ['boot.bin','app.bin','app.img','initial-spi.bin']:
 data=(b/name).read_bytes();meta['files'][name]={'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
(b/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta,indent=2))
