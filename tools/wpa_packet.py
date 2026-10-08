"""Trusted local UART envelope; never log or persist packet contents."""
import hashlib,secrets,zlib
def make_packet(ssid:bytes,ap:bytes,channel:int,passphrase:bytes)->bytearray:
    if not isinstance(ssid,bytes) or not 1<=len(ssid)<=32:raise ValueError('Invalid SSID size')
    if not isinstance(ap,bytes) or len(ap)!=6 or ap[0]&1 or not any(ap):raise ValueError('Invalid AP address')
    if not isinstance(channel,int) or not 1<=channel<=13:raise ValueError('Invalid channel')
    if not isinstance(passphrase,bytes) or not 8<=len(passphrase)<=63:raise ValueError('Invalid passphrase size')
    if any(c<32 or c>126 for c in passphrase):raise ValueError('Passphrase must contain printable ASCII')
    p=bytearray(148);p[:7]=b'TPMK'+bytes([1,channel,len(ssid)]);p[8:14]=ap;p[16:16+len(ssid)]=ssid
    p[48:80]=hashlib.pbkdf2_hmac('sha1',passphrase,ssid,4096,32);p[80:144]=secrets.token_bytes(64)
    p[144:]=zlib.crc32(p[:144]).to_bytes(4,'little');return p
def wipe_packet(packet:bytearray)->None:packet[:]=bytes(len(packet))
# Python immutable inputs/crypto temporaries cannot be reliably erased.
