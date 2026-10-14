/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t regs[256];
static unsigned operations,fail_at,writes;
static char output[8192];
void uart_puts(const char *s){assert(strlen(output)+strlen(s)<sizeof output);strcat(output,s);}
void uart_hex(uint32_t v){char s[9];snprintf(s,sizeof s,"%08x",v);uart_puts(s);}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t *v){
    assert(bank==0x61);operations++;
    if(operations==fail_at)return -1;
    *v=regs[reg];return 0;
}
int tuner_write_register(unsigned bank,unsigned reg,uint8_t v){
    assert(bank==0x61 && (reg==0xf3 || reg==0xf4 || reg==0xf5));
    if(reg==0xf3)assert(v==0xe0 || v==0xe3);
    if(reg==0xf4)assert(v<=2);
    operations++;writes++;regs[reg]=v;
    return operations==fail_at?-1:0; /* Failure after the device accepted it. */
}
int tuner_read_burst(unsigned bank,unsigned reg,uint8_t *p,unsigned n,unsigned *actual){
    assert(bank==0x61 && n<=8);operations++;*actual=0;
    if(operations==fail_at)return -1;
    for(unsigned i=0;i<n;i++)p[i]=regs[reg+i];
    *actual=n;return 0;
}
int tuner_read_burst_restart(unsigned bank,unsigned reg,uint8_t *p,unsigned n,unsigned *actual){
    return tuner_read_burst(bank,reg,p,n,actual);
}
int main(void){
    unsigned total=0;
    for(unsigned fail=0;fail<=total || !fail;fail++){
        memset(regs,0,sizeof regs);regs[0xf3]=0xe0;regs[0xf4]=2;regs[0xf5]=0x98;
        operations=writes=0;fail_at=fail;output[0]=0;
        tuner_program_address_probe();
        if(!fail){total=operations;assert(strstr(output,"read-restored-unclassified"));}
        else assert(!strstr(output,"status=read-restored-unclassified"));
        assert(regs[0xf3]==0xe0 && regs[0xf4]==2 && regs[0xf5]==0x98);
        if(fail && fail<=3)assert(!writes);
    }
    regs[0xf3]=0x23;operations=writes=fail_at=0;output[0]=0;
    tuner_program_address_probe();assert(!writes && strstr(output,"unexpected-state"));
    printf("PASS: address probe restoration, %u I/O failure positions, no payload/reset writes\n",total);
}
