"""Capture actual UART bytes with UTC timestamps; never generates sample logs."""
import argparse,datetime,pathlib,time
def main():
    import serial
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('port');p.add_argument('--baud',type=int,default=115200)
    p.add_argument('--seconds',type=float,default=30)
    p.add_argument('--output',default='logs/uart.txt')
    p.add_argument('--send',choices=['u','l','r'],help='Send one recovery/diagnostic UART command after opening')
    a=p.parse_args();dst=pathlib.Path(a.output);dst.parent.mkdir(parents=True,exist_ok=True)
    ser=serial.Serial(port=None,baudrate=a.baud,timeout=.1)
    ser.dtr=False;ser.rts=False;ser.port=a.port
    ser.open()
    with ser, dst.open('a',encoding='utf8') as f:
        if a.send:ser.write(a.send.encode('ascii'));ser.flush()
        deadline=time.monotonic()+a.seconds
        while time.monotonic()<deadline:
            raw=ser.readline()
            if raw:
                line=datetime.datetime.now(datetime.timezone.utc).isoformat()+' '+raw.decode('utf8',errors='backslashreplace')
                f.write(line);f.flush();print(line,end='')
if __name__=='__main__':main()
