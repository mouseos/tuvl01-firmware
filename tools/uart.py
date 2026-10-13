"""Development transport over the existing UART adapter; independent of native USB."""
import argparse,pathlib,re,struct,time,zlib

def validate(data):
    if len(data)<32:raise ValueError('Truncated image')
    magic,version,address,size,crc,entry,reserved,hcrc=struct.unpack('>8I',data[:32])
    if (magic,version,address,entry,reserved)!=(0x5455564c,1,0x1c000000,0x1c000000,0):raise ValueError('Invalid image target/header')
    if not 0<size<=0xfc000 or len(data)!=32+size:raise ValueError('Invalid image size')
    if zlib.crc32(data[:28])!=hcrc or zlib.crc32(data[32:])!=crc:raise ValueError('Image CRC mismatch')
    return data[:32],data[32:]

class Transport:
    def __init__(self,port,log):
        import serial
        self.log=log
        self.ser=serial.Serial(port=None,baudrate=115200,timeout=.1)
        self.ser.dtr=False;self.ser.rts=False;self.ser.port=port;self.ser.open()
        self.pending=b''
    def write(self,data):self.ser.write(data);self.ser.flush()
    def wait(self,predicate,timeout=5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            data=self.ser.readline()
            if data:
                self.log.write(data);self.log.flush()
                self.pending=getattr(self,'pending',b'')+data
                if len(self.pending)>4096:raise ValueError('UART line exceeds transport limit')
                if not self.pending.endswith(b'\n'):continue
                line=self.pending.decode('ascii',errors='backslashreplace').strip()
                self.pending=b''
                if line.startswith('UART rejected') or line.startswith('UART timeout'):raise RuntimeError(line)
                if predicate(line):return line
        raise TimeoutError('No expected UART response; reset into recovery if the transport was interrupted')
    def expect(self,line,timeout=5):return self.wait(lambda s:s==line,timeout)
    def recovery(self):
        self.ser.reset_input_buffer();self.pending=b'';self.write(b'i')
        mode=self.wait(lambda s:s.startswith('UART recovery ') or s=='UART application')
        if mode=='UART application':
            self.write(b'q');self.expect('TUVL01 independent recovery boot');self.write(b'i')
            # Standalone loader consumes the first byte to cancel autoboot.
            # Request its status again only after that cancellation is observed.
            mode=self.wait(lambda s:s.startswith('UART recovery ') or s=='AUTOBOOT cancelled',15)
            if mode=='AUTOBOOT cancelled':
                self.write(b'i');mode=self.wait(lambda s:s.startswith('UART recovery '),15)
        if not mode.endswith('busy=00000000'):raise RuntimeError('Recovery is busy; wait before retrying')
        return mode
    def resume(self,data):
        _,payload=validate(data)
        mode=self.recovery()
        match=re.fullmatch(r'UART recovery status=00000000 written=([0-9a-f]{8}) ready=00000000 busy=00000000',mode)
        if not match:raise RuntimeError('Recovery has no incomplete, error-free upload')
        offset=int(match[1],16)
        if offset>len(payload) or (offset!=len(payload) and offset%64):raise RuntimeError('Unexpected resume offset')
        print(f'Resuming RAM transfer at {offset} bytes')
        self.upload_chunks(payload,offset)
    def upload_chunks(self,payload,start=0):
        for offset in range(start,len(payload),64):
            chunk=payload[offset:offset+64]
            self.write(b'w');self.expect('UART chunk')
            self.write(struct.pack('>IH',offset,len(chunk)));self.expect('UART data')
            self.write(chunk);self.expect('UART accepted')
        self.write(b's');self.expect('UART sealed')
        print(f'RAM transfer and CRC verified: {len(payload)} bytes')
    def upload(self,data):
        header,payload=validate(data)
        self.recovery();self.write(b'b');self.expect('UART header');self.write(header);self.expect('UART accepted')
        self.upload_chunks(payload)
    def run(self):
        self.write(b'i')
        mode=self.wait(lambda s:s.startswith('UART recovery '))
        if 'ready=00000001 busy=00000000' not in mode:raise RuntimeError('Application is not validated')
        self.write(b'r');self.expect('RUN application CRC checked')
        self.expect('TUVL01 independent / FreeRTOS 11.1.0 / GNU SH2A BE')
        ticks=[]
        for _ in range(3):
            line=self.wait(lambda s:bool(re.fullmatch(r'RTOS tick=[0-9a-f]{8}',s)))
            ticks.append(int(line.split('=')[1],16))
        if any(not 0<((b-a)&0xffffffff)<10000 for a,b in zip(ticks,ticks[1:])):raise RuntimeError('RTOS ticks did not progress normally')
        print('UART RAM execution verified; RTOS ticks:',ticks)
    def save(self):
        self.write(b'p');self.expect('UART save queued')
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            self.write(b'i');line=self.wait(lambda s:s.startswith('UART recovery '))
            if line.endswith('busy=00000000'):
                if 'status=00000000 ' not in line:raise RuntimeError(line)
                print('Persistent application write/readback completed');return
            time.sleep(.1)
        raise TimeoutError('Flash update did not finish within 60 seconds')
    def load(self):
        self.recovery();self.write(b'l')
        self.wait(lambda s:s=='FLASH application validated; explicit run required')
        print('SPI application loaded into RAM and CRC verified')
    def audit(self):
        self.write(b'i');self.expect('UART application')
        self.write(b'f')
        print(self.wait(lambda s:bool(re.fullmatch(r'NOR protected_crc=[0-9a-f]{8}',s)),15))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    command_arg=p.add_argument('command',choices=['upload','resume','run','cycle','save','recover','diag','pins','sdio','wifi','mac','capability','scan','board','ap','apstop','load','audit','wifi-stats','wifi-verbose','wifi-clock','wifi-width','wifi-read-poll','wifi-write-poll','wifi-ts-feedback','wifi-nic-stats','wifi-link','wifi-rate','wifi-poll-reuse','wifi-status-poll','wifi-poll-budget','wifi-irq','wifi-read-check','tuner','tuner-board','tuner-analog','tuner-init','ts-burst','ts-aggregate','ts-probe','ts-output','ts-dma','ts-dma-long','ts-benchmark','ts-clock','ts-clock-max','icache','tuner-monitor','tuner-fec','tuner-quality','tmcc','uhf-base','vlow-base','serve','loader-update'])
    command_arg.choices += ['tuner-program-port','tuner-program-burst','tuner-program-release','tuner-program-restart','tuner-pin-capture','tuner-pin-test','tuner-pin-selftest']
    p.add_argument('--port',required=True);p.add_argument('--image',type=pathlib.Path)
    p.add_argument('--log',type=pathlib.Path,required=True)
    p.add_argument('--benchmark-seconds',type=int,
                   help='TS acquisition duration 1..300; requires variable-duration firmware')
    command_arg.choices.extend(['ais-channel','ais-auth','ais-assoc','ais-connect','wifi-restart'])
    p.add_argument('--ais-channel',type=int)
    p.add_argument('--ais-bssid',help='Explicit AP BSSID, colon-separated; no automatic selection')
    command_arg.choices.append('wifi-tx-window')
    command_arg.choices.append('wifi-queues')
    command_arg.choices.append('ts-test-source')
    command_arg.choices.append('ts-pipeline')
    command_arg.choices.extend(['ts-dma-source','ts-dma-fixed','quality-watch','quality-watch-dump'])
    command_arg.choices.append('wifi-station-stats')
    command_arg.choices.extend(['ts-frame-size','wifi-tx-timing'])
    command_arg.choices.append('wifi-rate-profile')
    command_arg.choices.append('wifi-cam')
    command_arg.choices.append('wifi-radio-debug')
    command_arg.choices.append('wifi-radio-groups')
    command_arg.choices.append('wifi-channel')
    command_arg.choices.append('wifi-channel-bssid')
    command_arg.choices.append('wifi-ht')
    command_arg.choices.append('wifi-io-timing')
    command_arg.choices.append('wifi-raw-tx')
    command_arg.choices.append('wifi-qos-tx')
    command_arg.choices.append('wifi-qos-class')
    command_arg.choices.append('wifi-fixed-mcs')
    command_arg.choices.append('wifi-more-data')
    command_arg.choices.append('wifi-credit-probe')
    command_arg.choices.append('wifi-dpd')
    command_arg.choices.append('wifi-rate-mailbox')
    command_arg.choices.append('wifi-auto-per')
    command_arg.choices.append('wifi-osc')
    command_arg.choices.append('wifi-tx-power')
    command_arg.choices.append('wifi-tx-ampdu')
    command_arg.choices.append('ts-state')
    command_arg.choices.append('wifi-clock-profile')
    command_arg.choices.append('wifi-idle-quality')
    command_arg.choices.append('wifi-quiet-quality')
    command_arg.choices.append('tuner-switch')
    command_arg.choices.append('rf-switch')
    command_arg.choices.append('tuner-reg')
    command_arg.choices.append('gpio-dump')
    command_arg.choices.extend(['gpio-drive','gpio-release','ts-group','wifi-tim'])
    p.add_argument('--group',type=int,default=128,help='ts-group: packets read between FIFO clears (32..224)')
    p.add_argument('--spbr',type=int,default=255,help='ts-group: RSPI1 SPBR to select first (0..254), 255 keeps the current value')
    p.add_argument('--gpio',help='gpio-drive: PORT+PIN such as B13 (ports A..H, pin 0..31); drives the opposite of the current level')
    p.add_argument('--reg',help='tuner-reg: BANK:REG for a read, BANK:REG=VALUE for a write (hex, bank 60..62, write reg<f0)')
    p.add_argument('--rf-switch',choices=['read','stock','inverse','alt','zero','pb16-low','pb16-high'],default='read',
                   help='PB14/PB15 for rf-switch: read-only, stock 1/0, inverse 0/1 (stops the tuner), or alt 1/1')
    command_arg.choices.extend(['wifi-rx-start','wifi-rx-stop','wifi-rx-stats'])
    a=p.parse_args()
    if a.benchmark_seconds is not None and (a.command!='ts-benchmark' or not 1<=a.benchmark_seconds<=300):
        p.error('--benchmark-seconds is valid only for ts-benchmark, with 1..300 seconds')
    ais_target=None
    if a.command in ('ais-channel','ais-auth','ais-assoc','ais-connect'):
        if a.ais_channel is None or not 1<=a.ais_channel<=13:p.error('--ais-channel must be 1..13')
        if not a.ais_bssid or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',a.ais_bssid):p.error('--ais-bssid must be a unicast MAC')
        mac=bytes.fromhex(a.ais_bssid.replace(':',''))
        if not any(mac) or mac[0]&1:p.error('--ais-bssid must be nonzero unicast')
        ais_target=bytes([a.ais_channel])+mac
    data=a.image.read_bytes() if a.image else None
    if a.command in ('upload','resume','cycle'):
        if data is None:p.error('--image is required')
        validate(data) # Reject a corrupt image before opening any device.
    a.log.parent.mkdir(parents=True,exist_ok=True)
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        try:
            if a.command=='ts-state':
                t.write(b'i');t.expect('UART application');t.write(bytes([18]))
                result=t.wait(lambda s:s.startswith('TS state end status='),10)
                print(result)
                if result!='TS state end status=read':raise RuntimeError(result)
                t.write(b'i');t.expect('UART application')
            if a.command=='wifi-restart':
                t.write(b'i');t.expect('UART application');t.write(b'|')
                result=t.wait(lambda s:s.startswith('WIFI restart end status='),60)
                print(result)
                if not result.endswith('=ready'):raise RuntimeError('Wi-Fi restart failed; see UART log')
                t.write(b'i');t.expect('UART application')
            if a.command in ('ais-channel','ais-auth','ais-assoc','ais-connect'):
                phase='channel' if a.command=='ais-channel' else 'auth'
                prefix='WIFI AIS '+phase
                t.write(b'i');t.expect('UART application')
                t.write(b'(' if a.command=='ais-connect' else b'"' if a.command=='ais-assoc' else b'{' if phase=='auth' else b'}')
                if a.command=='ais-connect':t.expect('WIFI AIS connection trial start; WPA2 not implemented')
                if a.command=='ais-assoc':t.expect('WIFI AIS association trial start; includes authentication')
                t.expect(prefix+' probe start')
                response=t.wait(lambda s:s==prefix+' target bytes=7' or s.startswith(prefix+' probe end status='))
                if response!=prefix+' target bytes=7':raise RuntimeError(response)
                t.write(ais_target)
                result=t.wait(lambda s:s.startswith(prefix+' probe end status='),15)
                if a.command=='ais-assoc':
                    trial=t.wait(lambda s:s.startswith('WIFI AIS association trial end status='))
                    if not trial.endswith('=ready'):raise RuntimeError('AIS association trial failed; see UART log')
                if a.command=='ais-connect':
                    trial=t.wait(lambda s:s.startswith('WIFI AIS connection trial end status='))
                    if not trial.endswith('=ready'):raise RuntimeError('AIS connection trial failed; see UART log')
                print(result)
                if not result.endswith('=ready'):raise RuntimeError('AIS '+phase+' probe failed; see UART log')
            if a.command in ('upload','cycle'):t.upload(data)
            if a.command=='resume':t.resume(data)
            if a.command in ('run','cycle'):t.run()
            if a.command=='save':t.save()
            if a.command=='recover':t.recovery()
            if a.command in ('tuner-program-port','tuner-program-burst','tuner-program-release','tuner-program-restart'):
                t.write(b'i');t.expect('UART application')
                opcode,prefix={
                    'tuner-program-port':(b'\x01','PROGRAM probe end status='),
                    'tuner-program-burst':(b'*','PROGRAM burst end status='),
                    'tuner-program-release':(b'.','PROGRAM release end status='),
                    'tuner-program-restart':(b'\x7f','PROGRAM restart end status='),
                }[a.command]
                t.write(opcode)
                result=t.wait(lambda s:s.startswith(prefix),30)
                print(result)
                expected='read-state-unchanged-unclassified' if a.command=='tuner-program-restart' else 'read-restored-unclassified'
                if result!=prefix+expected:raise RuntimeError(result)
                t.write(b'i');t.expect('UART application')
            if a.command in ('tuner-pin-capture','tuner-pin-test'):
                t.write(b'i');t.expect('UART application')
                test=a.command=='tuner-pin-test'
                t.write(b'-' if test else b'`')
                prefix='PINTST capture end status=' if test else 'PIN capture end status='
                result=t.wait(lambda s:s.startswith(prefix),30)
                print(result)
                if not result.endswith('=captured-restored-unclassified'):raise RuntimeError(result)
                t.write(b'i');t.expect('UART application')
            if a.command=='tuner-pin-selftest':
                t.write(b'i');t.expect('UART application');t.write(b',')
                result=t.wait(lambda s:s.startswith('PIN selftest end status='),10)
                print(result)
                if not result.endswith('=verified-restored'):raise RuntimeError(result)
                t.write(b'i');t.expect('UART application')
            if a.command=='diag':
                t.write(b'u');print(t.wait(lambda s:s.startswith('CLOCK FRQCR=')))
            if a.command=='pins':
                t.write(b'i');t.expect('UART application')
                t.write(b'g');print(t.wait(lambda s:s.startswith('USB GPIO ')))
            if a.command=='sdio':
                t.write(b'i');t.expect('UART application')
                t.write(b'd');t.expect('SDIO identification start; no wireless transmission')
                print(t.wait(lambda s:s=='SDIO identification end',15))
            if a.command=='wifi':
                t.write(b'i');t.expect('UART application')
                t.write(b'h');t.expect('WIFI boot start')
                result=t.wait(lambda s:s.startswith('WIFI boot end status='),60)
                print(result)
                if not result.endswith('=ready'):raise RuntimeError('Wi-Fi firmware startup failed; see UART log')
            if a.command=='mac':
                t.write(b'i');t.expect('UART application')
                t.write(b'm');t.expect('WIFI MAC query start')
                result=t.wait(lambda s:s.startswith('WIFI MAC query end status='),15)
                print(result)
                if not result.endswith('=ready'):raise RuntimeError('Wi-Fi MAC query failed; see UART log')
            if a.command in ('capability','scan'):
                t.write(b'i');t.expect('UART application')
                t.write(b'n' if a.command=='capability' else b'c')
                prefix='WIFI capability' if a.command=='capability' else 'WIFI passive scan'
                t.wait(lambda s:s.startswith(prefix+' start'))
                result=t.wait(lambda s:s.startswith(prefix+' end status='),20)
                print(result)
                if not result.endswith('=ready'):raise RuntimeError(prefix+' failed; see UART log')
            if a.command=='board':
                t.write(b'i');t.expect('UART application')
                t.write(b'b');t.expect('WIFI board configuration start')
                result=t.wait(lambda s:s.startswith('WIFI board configuration end status='),15)
                print(result)
                if not result.endswith('=transferred'):raise RuntimeError('Wi-Fi board configuration transfer failed; see UART log')
            if a.command in ('ap','apstop'):
                t.write(b'i');t.expect('UART application')
                t.write(b'a' if a.command=='ap' else b'x')
                prefix='WIFI AP' if a.command=='ap' else 'WIFI AP stop'
                t.expect(prefix+' start')
                result=t.wait(lambda s:s.startswith(prefix+' end status='),20)
                print(result)
                if not result.endswith('=transferred'):raise RuntimeError(prefix+' failed; see UART log')
            if a.command=='serve':
                # One command replaces the whole bring-up sequence (firmware src/tuner_serve.c).
                t.write(b'i');t.expect('UART application');t.write(bytes([16]))
                result=t.wait(lambda s:s.startswith('SERVE end status='),400)
                print(result)
                if not result.endswith('=ready'):raise RuntimeError('Bring-up failed; see UART log')
            if a.command=='loader-update':
                # Rewrites the 8 KiB boot loader (SPI NOR sectors 0 and 1) from the running application.
                if not a.image:raise RuntimeError('--image build/boot.bin is required')
                data=a.image.read_bytes()
                if len(data)>8192 or b'TUVL01 independent recovery boot' not in data:raise RuntimeError('Not a loader image')
                data=data.ljust(8192,b'\xff')
                payload=data+struct.pack('>I',zlib.crc32(data)&0xffffffff)
                t.write(b'i');t.expect('UART application');t.write(bytes([19]))
                t.wait(lambda s:s.startswith('LOADER update ready'),10)
                for i in range(0,len(payload),64):
                    t.write(payload[i:i+64]);t.wait(lambda s:s=='LOADER ack',10)
                result=t.wait(lambda s:s.startswith('LOADER update end status='),60)
                print(result)
                if not result.endswith('=verified'):raise RuntimeError('Loader update failed: '+result)
            if a.command=='load':t.load()
            if a.command=='audit':t.audit()
            if a.command in ('wifi-stats','wifi-verbose'):
                t.write(b'i');t.expect('UART application')
                t.write(b't' if a.command=='wifi-stats' else b'v')
                print(t.wait(lambda s:s.startswith('WIFI stats ' if a.command=='wifi-stats' else 'WIFI verbose=')))
                if a.command=='wifi-stats':
                    # Drain any additional diagnostics before closing the port.
                    t.write(b'i');t.expect('UART application')
            if a.command=='tuner-switch':
                t.write(b'i');t.expect('UART application');t.write(bytes([22]))
                result=t.wait(lambda s:s.startswith('TUNE switch end status='),20)
                print(result)
                if result!='TUNE switch end status=switched':raise RuntimeError(result)
                t.write(b'i');t.expect('UART application')
            if a.command=='gpio-drive':
                m=re.fullmatch(r'([A-Ha-h])([0-9]{1,2})',a.gpio or '')
                if not m or int(m[2])>31:p.error('--gpio must look like B13 (ports A..H, pin 0..31)')
                t.write(b'i');t.expect('UART application');t.write(bytes([28]));t.expect('GPIO drive start')
                t.write(bytes([ord(m[1].upper())-65,int(m[2]),2]))
                while True:
                    line=t.wait(lambda s:s.startswith('GPIO drive'),10);print(line)
                    if line.startswith('GPIO drive end status='):break
                if line!='GPIO drive end status=driven':raise RuntimeError(line)
                t.write(b'i');t.expect('UART application')
            if a.command=='ts-group':
                if not 1<=a.group<=224:p.error('--group must be 1..224')
                t.write(b'i');t.expect('UART application');t.write(bytes([30]));t.expect('TS group bench start')
                t.write(bytes([a.group,a.spbr]))
                print(t.wait(lambda s:s.startswith('TS group bench per-group') or s.startswith('TS group bench end status='),10))
                print(t.wait(lambda s:s.startswith('TS group bench group='),10))
                result=t.wait(lambda s:s.startswith('TS group bench end status='),5);print(result)
                t.write(b'i');t.expect('UART application')
            if a.command=='wifi-tim':
                t.write(b'i');t.expect('UART application');t.write(bytes([31]))
                result=t.wait(lambda s:s.startswith('WIFI TIM end status='),5);print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP before changing the beacon TIM')
            if a.command=='gpio-release':
                t.write(b'i');t.expect('UART application');t.write(bytes([29]))
                print(t.wait(lambda s:s.startswith('GPIO release end status='),5))
                t.write(b'i');t.expect('UART application')
            if a.command=='gpio-dump':
                t.write(b'i');t.expect('UART application');t.write(bytes([27]));t.expect('GPIO dump start')
                for _ in range(16):print(t.wait(lambda s:s.startswith('GPIO 0xfffe38') or s.startswith('GPIO fffe38') or s.startswith('GPIO ')))
                print(t.wait(lambda s:s.startswith('GPIO dump end status='),5))
                t.write(b'i');t.expect('UART application')
            if a.command=='tuner-reg':
                m=re.fullmatch(r'([0-9a-fA-F]{2}):([0-9a-fA-F]{2})(?:=([0-9a-fA-F]{2}))?',a.reg or '')
                if not m:p.error('--reg must be BANK:REG or BANK:REG=VALUE in hex')
                bank,reg=int(m[1],16),int(m[2],16)
                if not 0x60<=bank<=0x62 or (m[3] and reg>=0xf0):p.error('register is outside the diagnostic range')
                t.write(b'i');t.expect('UART application');t.write(bytes([26]));t.expect('REG access start')
                t.write(bytes([ord('w' if m[3] else 'r'),bank,reg,int(m[3] or '0',16)]))
                line=t.wait(lambda s:s.startswith('REG bank=') or s.startswith('REG access end status='),10)
                if line.startswith('REG bank='):
                    print(line);line=t.wait(lambda s:s.startswith('REG access end status='),10)
                print(line)
                t.write(b'i');t.expect('UART application')
                if line!='REG access end status=done':raise RuntimeError(line)
            if a.command=='rf-switch':
                t.write(b'i');t.expect('UART application');t.write(bytes([25]));t.expect('RF switch start')
                t.write({'read':b'r','stock':b's','inverse':b'i','alt':b'a','zero':b'z','pb16-low':b'l','pb16-high':b'h'}[a.rf_switch])
                result=t.wait(lambda s:s.startswith('RF switch end status='),10)
                print(result)
                t.write(b'i');t.expect('UART application')
                if result not in ('RF switch end status=read','RF switch end status='+a.rf_switch):raise RuntimeError(result)
            if a.command=='wifi-quiet-quality':
                t.write(b'i');t.expect('UART application');t.write(bytes([24]))
                result=t.wait(lambda s:s.startswith('WIFI quiet sample end status='),90)
                print(result)
                if result!='WIFI quiet sample end status=sampled-restarted':raise RuntimeError(result)
                t.write(b'i');t.expect('UART application')
            if a.command=='wifi-idle-quality':
                t.write(b'i');t.expect('UART application');t.write(bytes([21]))
                result=t.wait(lambda s:s.startswith('WIFI idle sample end status='),25)
                print(result)
                if result!='WIFI idle sample end status=restored':raise RuntimeError(result)
                t.write(b'i');t.expect('UART application')
            if a.command=='wifi-clock-profile':
                t.write(b'i');t.expect('UART application');t.write(bytes([20]))
                result=t.wait(lambda s:s.startswith('WIFI clock profile end status='),20)
                print(result)
                if result!='WIFI clock profile end status=ready':raise RuntimeError(result)
                t.write(b'i');t.expect('UART application')
            if a.command=='wifi-clock':
                t.write(b'i');t.expect('UART application');t.write(b'k')
                result=t.wait(lambda s:s.startswith('WIFI normal clock end status='),10)
                print(result)
                if not result.endswith('=ready'):raise RuntimeError('SDIO normal clock validation failed')
            if a.command=='wifi-width':
                t.write(b'i');t.expect('UART application');t.write(b'W')
                result=t.wait(lambda s:s.startswith('WIFI width end status='),15)
                print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=verified-reads'):raise RuntimeError('SDIO width probe failed; see restoration diagnostics')
            if a.command=='wifi-read-poll':
                t.write(b'i');t.expect('UART application');t.write(b'L')
                print(t.wait(lambda s:s.startswith('WIFI read polling='),10))
                t.write(b'i');t.expect('UART application')
            if a.command=='wifi-ts-feedback':
                t.write(b'i');t.expect('UART application');t.write(b'N')
                print(t.wait(lambda s:s.startswith('WIFI TS feedback enabled='),10))
                t.write(b'i');t.expect('UART application')
            if a.command=='wifi-nic-stats':
                t.write(b'i');t.expect('UART application');t.write(b'O')
                result=t.wait(lambda s:s.startswith('WIFI NIC statistics end status='),10)
                print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=ready'):raise RuntimeError('NIC statistics unavailable; see UART log')
            if a.command=='wifi-station-stats':
                t.write(b'i');t.expect('UART application');t.write(b'6')
                result=t.wait(lambda s:s.startswith('WIFI station stats end status='),15)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=read-raw'):raise RuntimeError('Station statistics unavailable; see UART log')
            if a.command=='wifi-link':
                t.write(b'i');t.expect('UART application');t.write(b'K')
                result=t.wait(lambda s:s.startswith('WIFI link quality end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=read'):raise RuntimeError('Link quality unavailable; see raw UART response')
            if a.command=='wifi-rate':
                t.write(b'i');t.expect('UART application');t.write(b'R')
                result=t.wait(lambda s:s.startswith('WIFI rate end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP before changing the rate comparison')
            if a.command=='wifi-rate-profile':
                t.write(b'i');t.expect('UART application');t.write(b'3')
                result=t.wait(lambda s:s.startswith('WIFI rate profile end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP and remove the peer before changing advertised rates')
            if a.command=='wifi-radio-debug':
                t.write(b'i');t.expect('UART application');t.write(b'1')
                result=t.wait(lambda s:s.startswith('WIFI radio debug end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=read-raw'):raise RuntimeError('Radio debug read unavailable; see raw UART log')
            if a.command=='wifi-radio-groups':
                t.write(b'i');t.expect('UART application');t.write(b'!')
                result=t.wait(lambda s:s.startswith('WIFI radio groups end status='),25)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=read-raw'):raise RuntimeError('Radio group read unavailable; see raw UART log')
            if a.command=='wifi-channel':
                t.write(b'i');t.expect('UART application');t.write(b'0')
                result=t.wait(lambda s:s.startswith('WIFI channel end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP/stream and drain credits before changing channel')
            if a.command=='wifi-cam':
                t.write(b'i');t.expect('UART application');t.write(b'2')
                result=t.wait(lambda s:s.startswith('WIFI CAM end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=transferred'):raise RuntimeError('CAM transfer refused or failed; use an active AP with no peer')
            if a.command in ('wifi-rx-start','wifi-rx-stop','wifi-rx-stats'):
                key,ending,expected={
                    'wifi-rx-start':(b'=','WIFI RX sink start end status=','started'),
                    'wifi-rx-stop':(b'_','WIFI RX sink stop end status=','stopped'),
                    'wifi-rx-stats':(b'+','WIFI RX sink stats end status=','read')}[a.command]
                t.write(b'i');t.expect('UART application');t.write(key)
                result=t.wait(lambda s:s.startswith(ending),10)
                print(result);t.write(b'i');t.expect('UART application')
                if result!=ending+expected:raise RuntimeError('RX sink command refused; stop TS and associate the peer first')
            if a.command=='wifi-auto-per':
                t.write(b'i');t.expect('UART application');t.write(b'$')
                result=t.wait(lambda s:s.startswith('WIFI auto PER end status='),15)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=transferred'):raise RuntimeError('Auto PER request incomplete; no automatic retry')
            if a.command=='wifi-osc':
                t.write(b'i');t.expect('UART application');t.write(bytes([6]))
                result=t.wait(lambda s:s.startswith('WIFI OSC end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=transferred'):raise RuntimeError('OSC request refused or failed; no automatic retry')
            if a.command=='wifi-rate-mailbox':
                t.write(b'i');t.expect('UART application');t.write(b'&')
                result=t.wait(lambda s:s.startswith('WIFI rate mailbox end status='),15)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=read-raw'):raise RuntimeError('Firmware mailbox read failed; raw UART result retained')
            if a.command=='wifi-dpd':
                t.write(b'i');t.expect('UART application');t.write(b'@')
                result=t.wait(lambda s:s.startswith('WIFI DPD request end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=transferred'):raise RuntimeError('DPD request refused or transfer failed; no automatic retry')
            if a.command=='wifi-credit-probe':
                t.write(b'i');t.expect('UART application');t.write(b']')
                result=t.wait(lambda s:s.startswith('WIFI credit probe end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP and use register status polling with all credits returned')
            if a.command=='wifi-more-data':
                t.write(b'i');t.expect('UART application');t.write(b'[')
                result=t.wait(lambda s:s.startswith('WIFI more data end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP/stream and select Ethernet TX before changing more-data')
            if a.command=='wifi-fixed-mcs':
                t.write(b'i');t.expect('UART application');t.write(b'/')
                result=t.wait(lambda s:s.startswith('WIFI fixed MCS end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP/stream, enable HT and disable legacy fixed rate before selecting fixed MCS')
            if a.command=='wifi-qos-class':
                t.write(b'i');t.expect('UART application');t.write(b';')
                result=t.wait(lambda s:s.startswith('WIFI QoS class end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP/stream, select QoS/HT and drain all credits before changing class')
            if a.command=='wifi-qos-tx':
                t.write(b'i');t.expect('UART application');t.write(b':')
                result=t.wait(lambda s:s.startswith('WIFI QoS TX end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP/stream, disable aggregation, select native TX and enable HT before QoS TX')
            if a.command=='wifi-raw-tx':
                t.write(b'i');t.expect('UART application');t.write(b'~')
                result=t.wait(lambda s:s.startswith('WIFI raw TX end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP/stream and disable aggregation before changing raw TX')
            if a.command=='wifi-io-timing':
                t.write(b'i');t.expect('UART application');t.write(b'^')
                result=t.wait(lambda s:s.startswith('WIFI IO timing end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop stream before changing IO timing')
            if a.command=='wifi-ht':
                t.write(b'i');t.expect('UART application');t.write(b'%')
                result=t.wait(lambda s:s.startswith('WIFI HT end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP before changing HT profile')
            if a.command=='wifi-channel-bssid':
                t.write(b'i');t.expect('UART application');t.write(b'?')
                result=t.wait(lambda s:s.startswith('WIFI channel BSSID end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP/stream and drain credits before changing request BSSID')
            if a.command=='wifi-poll-reuse':
                t.write(b'i');t.expect('UART application');t.write(b'Z')
                result=t.wait(lambda s:s.startswith('WIFI poll reuse end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP before changing poll reuse')
            if a.command=='wifi-irq':
                t.write(b'i');t.expect('UART application');t.write(b'X')
                result=t.wait(lambda s:s.startswith('WIFI IRQ end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP and verify HIF state before changing IRQ waits')
            if a.command=='wifi-tx-window':
                t.write(b'i');t.expect('UART application');t.write(b'9')
                result=t.wait(lambda s:s.startswith('WIFI TX window end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP and verify HIF credits before changing TX window')
            if a.command in ('ts-frame-size','wifi-tx-timing'):
                prefix,key=('TS frame size',b'5') if a.command=='ts-frame-size' else ('WIFI TX timing',b'4')
                t.write(b'i');t.expect('UART application');t.write(key)
                result=t.wait(lambda s:s.startswith(prefix+' end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Selection refused; stop streaming/AP and drain outstanding traffic')
            if a.command=='wifi-queues':
                t.write(b'i');t.expect('UART application');t.write(b'8')
                result=t.wait(lambda s:s.startswith('WIFI queues end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP before changing queue parameters')
            if a.command=='wifi-tx-power':
                t.write(b'i');t.expect('UART application');t.write(bytes([15]))
                result=t.wait(lambda s:s.startswith('WIFI TX power end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=transferred'):raise RuntimeError(result)
            if a.command=='wifi-tx-ampdu':
                t.write(b'i');t.expect('UART application');t.write(bytes([17]))
                result=t.wait(lambda s:s.startswith('WIFI TX AMPDU end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=transferred'):raise RuntimeError(result)
            if a.command in ('quality-watch','quality-watch-dump'):
                dump=a.command=='quality-watch-dump'
                t.write(b'i');t.expect('UART application');t.write(bytes([14 if dump else 13]))
                if dump:print(t.expect('QUALITY watch end status=raw',15))
                else:
                    result=t.wait(lambda s:s.startswith('QUALITY watch begin status='),10);print(result)
                    if not result.endswith('=armed'):raise RuntimeError('Quality sampler is already active')
                t.write(b'i');t.expect('UART application')
            if a.command in ('ts-dma-source','ts-dma-fixed'):
                fixed=a.command=='ts-dma-fixed';prefix='TS DMA fixed' if fixed else 'TS DMA source'
                t.write(b'i');t.expect('UART application');t.write(bytes([12 if fixed else 11]))
                result=t.wait(lambda s:s.startswith(prefix+' end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop TS, verify long DMA and enable pipeline before selecting DMA source')
            if a.command=='ts-pipeline':
                t.write(b'i');t.expect('UART application');t.write(bytes([9]))
                result=t.wait(lambda s:s.startswith('TS pipeline end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop TS and verify long DMA before enabling the pipeline')
            if a.command=='ts-test-source':
                t.write(b'i');t.expect('UART application');t.write(b'7')
                result=t.wait(lambda s:s.startswith('TS test source end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop TS streaming before selecting a test source')
            if a.command=='wifi-poll-budget':
                t.write(b'i');t.expect('UART application');t.write(b'G')
                result=t.wait(lambda s:s.startswith('WIFI poll budget end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP before changing poll budget')
            if a.command=='wifi-status-poll':
                t.write(b'i');t.expect('UART application');t.write(b'A')
                result=t.wait(lambda s:s.startswith('WIFI status poll end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('Stop AP and verify HIF state before changing status polling')
            if a.command=='ts-aggregate':
                t.write(b'i');t.expect('UART application');t.write(b'U')
                result=t.wait(lambda s:s.startswith('TS aggregate end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('TS aggregate selection failed')
            if a.command=='ts-burst':
                t.write(b'i');t.expect('UART application');t.write(b'S')
                result=t.wait(lambda s:s.startswith('TS burst end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=selected'):raise RuntimeError('TS burst selection failed')
            if a.command=='wifi-read-check':
                t.write(b'i');t.expect('UART application');t.write(b'P')
                result=t.wait(lambda s:s.startswith('WIFI read check end status='),40)
                print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=ready'):raise RuntimeError('SDIO read check failed; see UART log')
            if a.command=='ts-benchmark':
                t.write(b'i');t.expect('UART application')
                if a.benchmark_seconds is None:t.write(b'H')
                else:
                    t.write(b'\x05');t.expect('TS benchmark configuration bytes=12 version=1')
                    packet=b'TSB1'+struct.pack('>I',a.benchmark_seconds)
                    t.write(packet+struct.pack('>I',zlib.crc32(packet)))
                result=t.wait(lambda s:s.startswith('TS benchmark end status='),
                              20 if a.benchmark_seconds is None else a.benchmark_seconds+10)
                print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=measured'):raise RuntimeError('TS acquisition measurement failed; see UART log')
            if a.command in ('ts-clock','ts-clock-max'):
                t.write(b'i');t.expect('UART application');t.write(b'J' if a.command=='ts-clock-max' else b'C')
                result=t.wait(lambda s:s.startswith('TS clock end status='),15)
                print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=verified-loopback'):raise RuntimeError('SPI clock comparison failed; see UART log')
            if a.command=='icache':
                t.write(b'i');t.expect('UART application');t.write(b'I')
                result=t.wait(lambda s:s.startswith('ICACHE end status='),10)
                print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=ready'):raise RuntimeError('Instruction cache comparison failed; see UART log')
            if a.command=='ts-dma-long':
                t.write(b'i');t.expect('UART application');t.write(b'T')
                result=t.wait(lambda s:s.startswith('TS DMA long end status='),15)
                print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=verified'):raise RuntimeError('Longword DMA probe failed; see UART log')
            if a.command=='wifi-write-poll':
                t.write(b'i');t.expect('UART application');t.write(b'Y')
                print(t.wait(lambda s:s.startswith('WIFI write polling='),10))
                t.write(b'i');t.expect('UART application')
            if a.command in ('tuner','tuner-board'):
                t.write(b'i');t.expect('UART application');t.write(b'e' if a.command=='tuner' else b'j')
                result=t.wait(lambda s:s.startswith('TUNER probe end status='),10)
                print(result)
                if not result.endswith('=read'):raise RuntimeError('Tuner probe failed; see UART register diagnostics')
                t.write(b'i');t.expect('UART application')
                print('UART application remains active after tuner probe')
            if a.command=='tuner-analog':
                t.write(b'i');t.expect('UART application');t.write(b'o')
                result=t.wait(lambda s:s.startswith('TUNER analog end status='),15)
                print(result)
                t.write(b'i');t.expect('UART application')
                if not result.endswith('=calibrated'):raise RuntimeError('Analog stage incomplete; see UART readback and calibration status')
            if a.command=='tuner-init':
                t.write(b'i');t.expect('UART application');t.write(b'p')
                result=t.wait(lambda s:s.startswith('TUNER initialize end status='),180)
                print(result)
                t.write(b'i');t.expect('UART application')
                print('UART application remains active after tuner initialization')
                if not result.endswith('=calibrated'):raise RuntimeError('Tuner initialization incomplete; inspect patch parity and calibration log')
            if a.command=='tuner-fec':
                t.write(b'i');t.expect('UART application');t.write(b'M')
                result=t.wait(lambda s:s.startswith('FEC snapshot end status='),20)
                print(result);t.write(b'i');t.expect('UART application')
                if result.endswith('=i2c-failed'):raise RuntimeError(result)
            if a.command=='tuner-quality':
                t.write(b'i');t.expect('UART application');t.write(b'Q')
                result=t.wait(lambda s:s.startswith('QUALITY end status='),20)
                print(result);t.write(b'i');t.expect('UART application')
                if result.endswith(('=i2c-failed','=restore-failed')):raise RuntimeError(result)
            if a.command=='tuner-monitor':
                t.write(b'i');t.expect('UART application');t.write(b'y')
                result=t.wait(lambda s:s.startswith('TUNER monitor end status='),15)
                print(result);t.write(b'i');t.expect('UART application')
                if result.endswith('=i2c-failed'):raise RuntimeError(result)
            if a.command in ('tmcc','uhf-base','vlow-base'):
                t.write(b'i');t.expect('UART application')
                t.write({'tmcc':b'r','uhf-base':b'F','vlow-base':b'V'}[a.command])
                prefix='TMCC read' if a.command=='tmcc' else 'TUNER band base'
                result=t.wait(lambda s:s.startswith(prefix+' end status='),20)
                print(result);t.write(b'i');t.expect('UART application')
                if result.endswith(('=failed','=i2c-failed','=mismatch')):raise RuntimeError(result)
            if a.command=='ts-dma':
                t.write(b'i');t.expect('UART application');t.write(b'D')
                result=t.wait(lambda s:s.startswith('TS DMA probe end status='),10)
                print(result);t.write(b'i');t.expect('UART application')
                if not result.endswith('=verified'):raise RuntimeError('RSPI1 DMA loopback failed; see log')
            if a.command in ('ts-probe','ts-output'):
                probe=a.command=='ts-probe'
                t.write(b'i');t.expect('UART application');t.write(b's' if probe else b'z')
                result=t.wait(lambda s:s.startswith('TS probe end status=' if probe else 'TS output end status='),30)
                print(result)
                t.write(b'i');t.expect('UART application')
                print('UART application remains active after TS diagnostic')
                if result.endswith('=failed'):raise RuntimeError('TS diagnostic failed; inspect peripheral/FIFO log')
        finally:t.ser.close()
if __name__=='__main__':main()
