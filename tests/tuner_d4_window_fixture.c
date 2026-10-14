#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t regs[256];
static unsigned ops,fail_at,writes,times,persistent_restore,ignore_selection;
static char output[65536];
uint32_t board_time_counts(void){return ++times;}
void uart_puts(const char *s){
    if(!fail_at && times)assert(times%32==0);
    assert(strlen(output)+strlen(s)<sizeof output);strcat(output,s);
}
void uart_hex(uint32_t v){char s[9];snprintf(s,sizeof s,"%08x",v);uart_puts(s);}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t *value){
    assert(bank==0x61 && (reg==0xf3 || reg==0xf4 || reg==0xf5 || reg==0xd4 || reg==0xd5));
    if(++ops==fail_at)return -1;
    *value=reg==0xd5?0x20+((regs[0xd4]>>3)&7):regs[reg];return 0;
}
int tuner_write_register(unsigned bank,unsigned reg,uint8_t value){
    assert(bank==0x61 && (reg==0xf3 || reg==0xd4));ops++;writes++;
    if(reg==0xd4){
        assert(regs[0xf3]==0xe1);
        assert(value==0x97 || value==0x9f || value==0xa7 || value==0x87);
        if(persistent_restore && value==0x87)return -1;
        if(!ignore_selection || value==0x87)regs[reg]=value;
    }else {assert(value==0xe0 || value==0xe3);regs[reg]=value==0xe3?0xe1:value;}
    return ops==fail_at?-1:0; /* Error after possible acceptance. */
}
static void reset(void){
    memset(regs,0,sizeof regs);regs[0xd4]=0x87;regs[0xf3]=0xe0;regs[0xf4]=2;regs[0xf5]=0x98;
    ops=writes=times=0;output[0]=0;
}
int main(void){
    unsigned total=0;
    for(unsigned fail=0;!fail || fail<=total;fail++){
        reset();fail_at=fail;tuner_d4_window_halted();
        if(!fail){total=ops;assert(times==160 && strstr(output,"status=read-restored-unclassified"));
            assert(strstr(output,"phase=00000003 requested=000000a7"));
            assert(strstr(output,"phase=00000004 index=0000000f"));}
        assert(regs[0xd4]==0x87 && regs[0xf3]==0xe0 && regs[0xf4]==2 && regs[0xf5]==0x98);
    }
    reset();fail_at=0;regs[0xf3]=0x23;tuner_d4_window_halted();assert(!writes && strstr(output,"unexpected-state"));
    reset();ignore_selection=1;tuner_d4_window_halted();
    assert(strstr(output,"requested=00000097 observed=00000087"));
    assert(!strstr(output,"block phase=00000002"));
    assert(regs[0xf3]==0xe0 && regs[0xd4]==0x87 && strstr(output,"read-failed-restored"));ignore_selection=0;
    reset();persistent_restore=1;tuner_d4_window_halted();
    assert(regs[0xf3]==0xe1 && strstr(output,"restore-failed-reinitialize-required"));
    printf("PASS: halted D4 window, %u single I/O failures, 80 buffered rows, selection guard and persistent restore halt\n",total);
}
