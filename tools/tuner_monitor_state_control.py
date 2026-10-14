"""Finite normal-reload control with read-only demod snapshots; no IQ claim."""
import argparse,json,pathlib
from uart import Transport
from tuner_mailbox_probe import normal
from tuner_pattern_capture import register,capture
from ts_capture import inspect

REGISTERS=[(0x60,0xb9)]+[(0x61,r) for r in
    (0x94,0x95,0x96,0x97,0x84,0xf3,0xf4,0xf5,0xd6,0xd7,0xda,0xdb)]

def snapshot(t):
    # Separate UART transactions: these are not a simultaneous state latch.
    return {f'{bank:02x}:{reg:02x}':register(t,bank,reg) for bank,reg in REGISTERS}

def control(t,output,report,cycles=2):
    if cycles not in (1,2):raise ValueError('Choose one or two reload cycles')
    report.update(scope='Normal-reload-only control; no monitor selector/PSEQ halt diagnostic',
                  iq_identified=False,cycles=[])
    for index in range(cycles):
        row={'cycle':index};report['cycles'].append(row)
        row['before']=snapshot(t)
        row['reload']=normal(t)
        row['after']=snapshot(t)
        try:
            data,summary=capture(t,output/f'normal-{index}.ts')
            row['capture']={**summary,**(inspect(data) if data else {})}
        except Exception as error:
            row['capture_error']=str(error)
        finally:
            t.write(b'i');t.expect('UART application');row['uart_responding']=True
        row['after_capture']=snapshot(t)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--log',required=True,type=pathlib.Path)
    p.add_argument('--output-dir',required=True,type=pathlib.Path)
    p.add_argument('--cycles',choices=(1,2),default=2,type=int)
    a=p.parse_args();a.log.parent.mkdir(parents=True,exist_ok=True)
    a.output_dir.mkdir(parents=True,exist_ok=True);report={'iq_identified':False}
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        try:
            t.write(b'i');t.expect('UART application')
            control(t,a.output_dir,report,a.cycles)
        except Exception as error:
            report['error']=str(error);raise
        finally:
            t.ser.close()
            (a.output_dir/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
