/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t regs[256];
static unsigned ops,fail_at,writes,persistent_restore,short_read;
static char output[32768];
void uart_puts(const char *s){assert(strlen(output)+strlen(s)<sizeof output);strcat(output,s);}
void uart_hex(uint32_t v){char s[9];snprintf(s,sizeof s,"%08x",v);uart_puts(s);}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t *v){
    assert(bank==0x61 && (reg==0x84 || reg==0xf3 || reg==0xf4 || reg==0xf5));
    if(++ops==fail_at)return -1;
    *v=regs[reg];return 0;
}
int tuner_write_register(unsigned bank,unsigned reg,uint8_t v){
    assert(bank==0x61 && (reg==0x84 || reg==0xf3));ops++;writes++;
    if(persistent_restore && reg==0x84 && v==0x80)return -1;
    if(reg==0x84){assert(regs[0xf3]==0xe1);regs[reg]=v;}
    else {assert(v==0xe0 || v==0xe3);regs[reg]=v==0xe3?0xe1:v;}
    return ops==fail_at?-1:0; /* Accepted write followed by transport error. */
}
int tuner_read_burst_restart(unsigned bank,unsigned reg,uint8_t *bytes,unsigned count,unsigned *received){
    assert(bank==0x61 && reg==0xba && count==2);ops++;
    *received=0;if(ops==fail_at)return -1;
    bytes[0]=regs[0x84];bytes[1]=regs[0x84]^0x55;
    *received=short_read?1:2;return 0;
}
static void reset(void){
    memset(regs,0,sizeof regs);regs[0xf3]=0xe0;regs[0xf4]=2;regs[0xf5]=0x98;regs[0x84]=0x80;
    ops=writes=0;output[0]=0;
}
int main(void){
    unsigned total=0;
    for(unsigned fail=0;!fail || fail<=total;fail++){
        reset();fail_at=fail;tuner_monitor_window_probe();
        if(!fail){total=ops;assert(strstr(output,"status=read-restored-unclassified"));
            assert(strstr(output,"phase=00000001 index=00000000 selector=00000000 ba=00000000 bb=00000055"));
            assert(strstr(output,"phase=00000002 index=00000000 selector=00000003 ba=00000003 bb=00000056"));}
        assert(regs[0x84]==0x80 && regs[0xf3]==0xe0 && regs[0xf4]==2 && regs[0xf5]==0x98);
        /* Recovery-only transient failures may still produce success. */
    }
    reset();fail_at=0;regs[0xf3]=0x23;tuner_monitor_window_probe();
    assert(!writes && strstr(output,"unexpected-state"));
    reset();short_read=1;tuner_monitor_window_probe();
    assert(!writes && strstr(output,"baseline-read-failed"));short_read=0;
    reset();persistent_restore=1;tuner_monitor_window_probe();
    assert(regs[0xf3]==0xe1 && strstr(output,"restore-failed-reinitialize-required"));
    printf("PASS: monitor window %u uncertain I/O failures, finite phases, guard, short read and persistent restore halt\n",total);
}
