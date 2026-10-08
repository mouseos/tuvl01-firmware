"""Local experimental USB EP0 uploader. Requires PyUSB + libusb/WinUSB."""
import argparse,json,pathlib,struct,time,zlib
MAGIC=0x5455564c
BOOT=0x424f4f54
APP=0x41505031
def validate_image(data):
    if len(data)<33: raise ValueError('truncated image')
    h=struct.unpack('>8I',data[:32])
    magic,version,addr,n,crc,entry,reserved,hcrc=h
    if magic!=MAGIC or version!=1 or addr!=0x1c000000 or entry!=addr or reserved or not 0<n<=0xfc000:
        raise ValueError('invalid image header or RAM range')
    if len(data)!=n+32 or zlib.crc32(data[:28])!=hcrc or zlib.crc32(data[32:])!=crc:
        raise ValueError('image length or CRC mismatch')
    return h
class Device:
    def __init__(self,vid=0xffff,pid=1):
        import usb.core
        import libusb_package
        self.core=usb.core
        self.find=libusb_package.find
        self.vid,self.pid=vid,pid
        self.dev=None
        self.connect()
    def connect(self):
        candidates=list(self.find(find_all=True,idVendor=self.vid,idProduct=self.pid))
        if len(candidates)!=1: raise RuntimeError(f'expected one device; found {len(candidates)}')
        self.dev=candidates[0]
        self.dev.set_configuration(1)
    def command(self,req,data=b'',offset=0):
        return self.dev.ctrl_transfer(0x40,req,offset&65535,offset>>16,data,timeout=3000)
    def info(self):
        v=struct.unpack('>8I',bytes(self.dev.ctrl_transfer(0xc0,1,0,0,32,timeout=3000)))
        if v[0]!=MAGIC or v[1]!=1:raise RuntimeError('unexpected protocol')
        return dict(zip(['magic','version','status','bytes_or_ticks','ready','update_state','jedec','mode'],v))
    def await_mode(self,mode):
        # A run/recover transition intentionally disconnects and re-enumerates.
        self.dev=None
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            time.sleep(.25)
            try:
                self.connect()
                if self.info()['mode']==mode:return
            except (self.core.USBError,RuntimeError):pass
        raise TimeoutError('device did not return in expected mode')
    def recovery(self):
        if self.info()['mode']==APP:
            self.command(8);self.await_mode(BOOT)
    def upload(self,path):
        data=pathlib.Path(path).read_bytes();validate_image(data)
        self.recovery()
        self.command(2,data[:32])
        payload=data[32:]
        for i in range(0,len(payload),64):self.command(3,payload[i:i+64],i)
        self.command(4)
        info=self.info()
        if info['status'] or not info['ready'] or info['bytes_or_ticks']!=len(payload):
            raise RuntimeError(f'RAM verification failed: {info}')
    def run(self):
        self.command(5);self.await_mode(APP)
        first=self.info()['bytes_or_ticks'];time.sleep(1.1)
        last=self.info()['bytes_or_ticks']
        if first==last:raise RuntimeError('RTOS tick did not advance')
        return self.info()
    def save(self):
        self.command(6)
        time.sleep(.05) # allow post-status deferred update to begin
        return self.await_operation()
    def load(self):
        self.command(7)
        time.sleep(.05)
        result=self.await_operation()
        if not result['ready']:raise RuntimeError('flash application not ready')
        return result
    def await_operation(self):
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            info=self.info()
            if not info['update_state']:
                if info['status']:raise RuntimeError(f'flash operation failed: {info}')
                return info
            time.sleep(.05)
        raise TimeoutError('flash operation deadline exceeded')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vid',type=lambda s:int(s,0),default=0xffff)
    p.add_argument('--pid',type=lambda s:int(s,0),default=1)
    p.add_argument('command',choices=['info','upload','run','save','load','recover','cycle'])
    p.add_argument('image',nargs='?')
    args=p.parse_args()
    if args.command in ('upload','cycle') and not args.image:p.error('image required')
    d=Device(args.vid,args.pid)
    if args.command=='recover':d.recovery()
    if args.command in ('upload','cycle'):d.upload(args.image)
    if args.command in ('run','cycle'):print(json.dumps(d.run()))
    if args.command=='save':d.recovery();d.save()
    if args.command=='load':d.recovery();d.load()
    print(json.dumps(d.info(),indent=2))
if __name__=='__main__':main()
