"""Summarize finite PD4..7 captures saved by tools/uart.py; values are not IQ."""
import argparse,json,pathlib,re,statistics

def summarize(text):
    start=text.rfind('PIN capture start PD4..7 input-only')
    if start<0:raise ValueError('No pin capture in log')
    capture=text[start:]
    if 'PIN capture end status=captured-restored-unclassified' not in capture:
        raise ValueError('No complete capture with confirmed restoration')
    samples={2:[],0:[]}
    pattern=r'^PIN sample mode=([0-9a-f]{8}) index=([0-9a-f]{8}) counts=([0-9a-f]{8}) value=([0-9a-f]{8})$'
    for line in capture.splitlines():
        if not line.startswith('PIN sample '):continue
        match=re.fullmatch(pattern,line)
        if not match:raise ValueError('Malformed sample line')
        mode,index,count,value=(int(v,16) for v in match.groups())
        if mode not in samples or value>15 or index!=len(samples[mode]):raise ValueError('Invalid sample order/value')
        samples[mode].append((count,value))
    result={'classification':'unclassified GPIO levels, not verified IQ',
            'timing':'timestamp before GPIO read; nonuniform software sampling; nominal CMT 4.5 MHz',
            'modes':[]}
    for mode,rows in samples.items():
        if len(rows)!=512:raise ValueError('Expected 512 samples per mode')
        intervals=[(b[0]-a[0])&0xffffffff for a,b in zip(rows,rows[1:])]
        if any(v>=0x80000000 for v in intervals):raise ValueError('Timestamp moved backwards')
        pin_stats=[]
        for bit in range(4):
            levels=[(row[1]>>bit)&1 for row in rows]
            pin_stats.append({'pin':'PD'+str(4+bit),'high_samples':sum(levels),
                              'observed_transitions':sum(a!=b for a,b in zip(levels,levels[1:]))})
        result['modes'].append({'e8_low_nibble':mode,'samples':len(rows),
                               'span_counts':sum(intervals),
                               'interval_counts_min':min(intervals),'interval_counts_median':statistics.median(intervals),
                               'interval_counts_max':max(intervals),'pins':pin_stats})
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=pathlib.Path)
    a=p.parse_args();print(json.dumps(summarize(a.log.read_text(encoding='ascii')),indent=2))

if __name__=='__main__':main()
