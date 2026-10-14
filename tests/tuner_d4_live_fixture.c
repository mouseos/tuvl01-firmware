#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t regs[256];
static unsigned ops,fail_at,writes,times,acquiring,ignore_selection,persistent_restore,race;
static char output[65536];
uint32_t board_time_counts(void){acquiring=!acquiring;return ++times;}
void uart_puts(const char *s){
    if(!fail_at)assert(!acquiring);
    assert(strlen(output)+strlen(s)<sizeof output);strcat(output,s);
}
void uart_hex(uint32_t v){char s[9];snprintf(s,sizeof s,"%08x",v);uart_puts(s);}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t *value){
    assert(bank==0x61 && (reg==0xf3 || reg==0xf4 || reg==0xf5 || reg==0xd4 || reg==0xd5));
    if(++ops==fail_at){acquiring=0;return -1;}
    if(race && writes==1 && reg==0xd5)regs[0xd4]=0x1e;
    *value=reg==0xd5?0x20+((regs[0xd4]>>3)&7):regs[reg];return 0;
}
int tuner_write_register(unsigned bank,unsigned reg,uint8_t value){
    /* The live entry point never halts PSEQ or writes program addresses. */
    assert(bank==0x61 && reg==0xd4 && regs[0xf3]==0xe0);ops++;writes++;
    assert(value==0x0e || value==0x2e || value==0x36 || value==0x16 || value==0x1e || value==0x26);
    if(persistent_restore && writes>1 && value==0x1e)return -1;
    if(!ignore_selection || value==0x1e)regs[reg]=value;
    return ops==fail_at?-1:0; /* Accepted before an uncertain error. */
}
static void reset(void){
    memset(regs,0,sizeof regs);regs[0xd4]=0x1e;regs[0xf3]=0xe0;regs[0xf4]=2;regs[0xf5]=0x98;
    ops=writes=times=acquiring=0;output[0]=0;
}
int main(void){
    unsigned total=0;
    for(unsigned fail=0;!fail || fail<=total;fail++){
        reset();fail_at=fail;tuner_d4_window_live_buffered();
        if(!fail){total=ops;assert(times==128);
            assert(strstr(output,"phase=00000006 index=00000007 selector=00000004"));
            assert(strstr(output,"read-restored-unclassified-reinitialize-required"));}
        assert(regs[0xd4]==0x1e && regs[0xf3]==0xe0 && regs[0xf4]==2 && regs[0xf5]==0x98);
    }
    fail_at=0;reset();ignore_selection=1;tuner_d4_window_live_buffered();
    assert(strstr(output,"requested=0000000e observed=0000001e"));
    assert(!strstr(output,"block phase=00000002") && regs[0xd4]==0x1e);ignore_selection=0;
    reset();race=1;tuner_d4_window_live_buffered();
    assert(strstr(output,"selector=00000001 requested=0000000e first=0000000e"));
    assert(strstr(output,"last=0000001e") && strstr(output,"selected=00000000"));
    assert(!strstr(output,"block phase=00000002") && regs[0xd4]==0x1e);race=0;
    reset();ignore_selection=1;persistent_restore=1;tuner_d4_window_live_buffered();
    assert(strstr(output,"restore-failed-reinitialize-required") && regs[0xf3]==0xe0);
    ignore_selection=persistent_restore=0;
    reset();regs[0xf3]=0x23;tuner_d4_window_live_buffered();assert(!writes);
    printf("PASS: live D4 buffer, %u uncertain I/O failures,64 rows, mismatch retention/abort, no PSEQ control writes\n",total);
}
