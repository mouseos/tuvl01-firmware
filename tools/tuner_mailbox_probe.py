"""Finite experimental PSEQ operand readout, with full normal patch reload.

Requires opcode0x81 RAM firmware. Runs normal SERVE/default channel14 before
and after the diagnostic. This verifies a candidate bridge, not IQ samples.
"""
import argparse,json,pathlib
from uart import Transport
from tuner_pattern_capture import capture
from ts_capture import inspect

def normal(t):
    t.write(bytes([16]))
    result=t.wait(lambda s:s.startswith('SERVE end status='),90)
    if result!='SERVE end status=ready':raise RuntimeError(result)
    t.write(b'E');t.wait(lambda s:s.startswith('TS stream end status='),15)
    return result

def probe(t,output,report=None):
    if report is None:report={}
    report.update(iq_identified=False,initialization=normal(t))
    try:
        t.write(b'\x81')
        report['probe']=t.wait(lambda s:s.startswith('MAILBOX probe end status='),30)
    finally:
        # Even a timed-out or failed probe may have modified chip RAM.
        report['normal_reload']=normal(t)
        data,summary=capture(t,output)
        report['normal_capture']={**summary,**(inspect(data) if data else {})}
        t.write(b'i');t.expect('UART application');report['uart_responding']=True
    if report['probe']!='MAILBOX probe end status=read-restored-unclassified-reinitialize-required':
        raise RuntimeError(report['probe'])
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--log',required=True,type=pathlib.Path)
    p.add_argument('--output-dir',required=True,type=pathlib.Path)
    a=p.parse_args();a.log.parent.mkdir(parents=True,exist_ok=True)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        report={'iq_identified':False}
        try:
            t.write(b'i');t.expect('UART application')
            probe(t,a.output_dir/'normal.ts',report)
            print(json.dumps(report,indent=2))
        except Exception as error:
            report['error']=str(error)
            raise
        finally:
            t.ser.close()
            (a.output_dir/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
