"""Finite known 84=00/03 -> BA/BB comparison, RAM opcode0x83; IQ unproven."""
import argparse,json,pathlib,re
from uart import Transport
from tuner_mailbox_probe import normal
from tuner_pattern_capture import capture
from ts_capture import inspect

def probe(t,output,report=None,updates=False,timing=False):
    if updates and timing:raise ValueError('Choose updates or timing')
    if report is None:report={}
    report.update(iq_identified=False,initialization=normal(t))
    report['updates']=updates
    report['timing']=timing
    try:
        t.write(b'\x86' if timing else b'\x85' if updates else b'\x83')
        report['probe']=t.wait(lambda s:s.startswith('MONWIN probe end status='),60 if updates or timing else 30)
    finally:
        report['normal_reload']=normal(t)
        try:
            data,summary=capture(t,output)
            report['normal_capture']={**summary,**(inspect(data) if data else {})}
        except Exception as error:
            report['capture_error']=str(error)
            raise
        finally:
            t.write(b'i');t.expect('UART application');report['uart_responding']=True
    if report['probe']!='MONWIN probe end status=read-restored-unclassified-reinitialize-required':
        raise RuntimeError(report['probe'])
    return report

def observations(raw):
    pattern=rb'^MONWIN sample phase=([0-9a-f]{8}) index=([0-9a-f]{8}) selector=([0-9a-f]{8}) ba=([0-9a-f]{8}) bb=([0-9a-f]{8})\r?$'
    blocks=rb'^MONWIN block phase=([0-9a-f]{8}) requested=([0-9a-f]{8}) reselect=([0-9a-f]{8})\r?$'
    times=rb'^MONWIN time phase=([0-9a-f]{8}) index=([0-9a-f]{8}) before=([0-9a-f]{8}) after=([0-9a-f]{8})\r?$'
    buffers=rb'^MONWIN buffered phase=([0-9a-f]{8}) pause_ms=([0-9a-f]{8})\r?$'
    return {'scope':'Complete rows only; bus pair coherence and IQ/sample rate unproven',
            'times':[dict(zip(['phase','index','before','after'],[int(x,16) for x in m])) for m in re.findall(times,raw,re.M)],
            'buffered':[dict(zip(['phase','pause_ms'],[int(x,16) for x in m])) for m in re.findall(buffers,raw,re.M)],
            'blocks':[dict(zip(['phase','requested','reselect'],[int(x,16) for x in m]))
                      for m in re.findall(blocks,raw,re.M)],
            'rows':[dict(zip(['phase','index','selector','ba','bb'],[int(x,16) for x in m]))
                    for m in re.findall(pattern,raw,re.M)]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--log',required=True,type=pathlib.Path)
    p.add_argument('--output-dir',required=True,type=pathlib.Path)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--updates',action='store_true',help='Compare repeated writes/edges of 00..03 and unverified 04..07; opcode0x85')
    mode.add_argument('--timing',action='store_true',help='Buffer selector 01/04 reads with no UART per read; compare zero/10ms delays and rewrites; opcode0x86')
    a=p.parse_args();a.log.parent.mkdir(parents=True,exist_ok=True)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    offset=a.log.stat().st_size if a.log.exists() else 0
    report={'iq_identified':False}
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        try:
            t.write(b'i');t.expect('UART application')
            probe(t,a.output_dir/'normal.ts',report,a.updates,a.timing)
        except Exception as error:
            report['error']=str(error);raise
        finally:
            t.ser.close();log.flush()
            report['observations']=observations(a.log.read_bytes()[offset:])
            (a.output_dir/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
