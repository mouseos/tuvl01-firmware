"""Finite known 84=00/03 -> BA/BB comparison, RAM opcode0x83; IQ unproven."""
import argparse,json,pathlib,re
from uart import Transport
from tuner_mailbox_probe import normal
from tuner_pattern_capture import capture
from ts_capture import inspect

def probe(t,output,report=None):
    if report is None:report={}
    report.update(iq_identified=False,initialization=normal(t))
    try:
        t.write(b'\x83')
        report['probe']=t.wait(lambda s:s.startswith('MONWIN probe end status='),30)
    finally:
        report['normal_reload']=normal(t)
        data,summary=capture(t,output)
        report['normal_capture']={**summary,**(inspect(data) if data else {})}
        t.write(b'i');t.expect('UART application');report['uart_responding']=True
    if report['probe']!='MONWIN probe end status=read-restored-unclassified-reinitialize-required':
        raise RuntimeError(report['probe'])
    return report

def observations(raw):
    pattern=rb'^MONWIN sample phase=([0-9a-f]{8}) index=([0-9a-f]{8}) selector=([0-9a-f]{8}) ba=([0-9a-f]{8}) bb=([0-9a-f]{8})\r?$'
    return {'scope':'Complete rows only; bus pair coherence and IQ/sample rate unproven',
            'rows':[dict(zip(['phase','index','selector','ba','bb'],[int(x,16) for x in m]))
                    for m in re.findall(pattern,raw,re.M)]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--log',required=True,type=pathlib.Path)
    p.add_argument('--output-dir',required=True,type=pathlib.Path)
    a=p.parse_args();a.log.parent.mkdir(parents=True,exist_ok=True)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    offset=a.log.stat().st_size if a.log.exists() else 0
    report={'iq_identified':False}
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        try:
            t.write(b'i');t.expect('UART application')
            probe(t,a.output_dir/'normal.ts',report)
        except Exception as error:
            report['error']=str(error);raise
        finally:
            t.ser.close();log.flush()
            report['observations']=observations(a.log.read_bytes()[offset:])
            (a.output_dir/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
