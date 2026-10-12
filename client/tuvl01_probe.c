/* SPDX-License-Identifier: MIT
 * Command-line client built on the portable core: HELLO, START, receive, STOP.
 * Usage: tuvl01_probe [seconds] [output.ts] */
#include "tuvl01_session.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv){
    int seconds=argc>1?atoi(argv[1]):5;
    FILE *out=argc>2?fopen(argv[2],"wb"):0;
    tuvl01_session s;tuvl01_reply r;
    int rc=tuvl01_open(&s);if(rc){fprintf(stderr,"open failed %d\n",rc);return 2;}
    rc=tuvl01_command(&s,TUVL01_OP_HELLO,&r,1500);
    if(rc){fprintf(stderr,"HELLO failed %d (is this PC on the TUVL01 network?)\n",rc);return 3;}
    printf("HELLO version=%u revision=%u caps=0x%x stream_port=%u state=%u\n",r.version,r.revision,r.caps,r.stream_port,r.state);
    rc=tuvl01_command(&s,TUVL01_OP_START,&r,1500);printf("START rc=%d state=%u\n",rc,r.state);
    uint8_t buffer[1344];uint64_t start=tuvl01_now_ms(),last=start,bytes=0,total=0;
    while(tuvl01_now_ms()-start<(uint64_t)seconds*1000){
        int n=tuvl01_receive(&s,buffer,sizeof buffer,5);
        if(n>0){bytes+=(uint64_t)n;total+=(uint64_t)n;if(out)fwrite(buffer,1,(size_t)n,out);}
        tuvl01_service(&s,10,1000);
        uint64_t now=tuvl01_now_ms();
        if(now-last>=1000){printf("  %.2f Mbps datagrams=%llu missing=%llu\n",bytes*8.0/1e6/((now-last)/1000.0),
            (unsigned long long)s.loss.datagrams,(unsigned long long)s.loss.missing);bytes=0;last=now;}
    }
    rc=tuvl01_command(&s,TUVL01_OP_STOP,&r,1500);printf("STOP rc=%d\n",rc);
    printf("total %llu bytes, datagrams=%llu missing=%llu invalid=%llu resyncs=%llu\n",(unsigned long long)total,
        (unsigned long long)s.loss.datagrams,(unsigned long long)s.loss.missing,
        (unsigned long long)s.loss.invalid,(unsigned long long)s.loss.resyncs);
    if(out)fclose(out);
    tuvl01_close(&s);return total?0:1;
}
