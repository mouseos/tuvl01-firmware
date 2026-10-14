/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
#include "tuner_pseq.h"
static uint8_t regs[256],memory[8192];
static unsigned ops,fail_at,cursor,parity,writes,source_ok=1,ignore_address,persistent_restore;
static unsigned restore_start;
static unsigned delayed_parity,persistent_changed_parity,parity_reads;
static unsigned payload_expected,halt_writes,current_operand,bursts;
static int uart_index=-1;
static uint32_t ticks;
int uart_getc(void){int v=uart_index;uart_index=-1;return v;}
uint32_t xTaskGetTickCount(void){return ticks;}
void vTaskDelay(uint32_t n){ticks+=n;}
static char output[262144];
void uart_puts(const char *s){
    if(!strcmp(s,"MAILBOX transfer operand="))halt_writes=0;
    assert(strlen(output)+strlen(s)<sizeof output);strcat(output,s);
}
void uart_hex(uint32_t v){
    const char *marker="MAILBOX transfer operand=";size_t n=strlen(output),m=strlen(marker);
    if(n>=m && !strcmp(output+n-m,marker))current_operand=v;
    if(v==0x0f0d && n>=m && !strcmp(output+n-m,marker) && !restore_start)restore_start=ops+1;
    char s[9];snprintf(s,sizeof s,"%08x",v);uart_puts(s);
}
int tuner_program_mailbox_original_valid(void){return source_ok;}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t *v){
    assert(!payload_expected); /* No register read between arm and payload. */
    assert(bank==0x61 || (bank==0x60 && reg==0x6d));
    ops++;if(ops==fail_at)return -1;
    *v=reg==0xf8?(parity!=0)<<4:reg==0x6d?(bank==0x60?7:memory[0x4e9]==0x0c?42:8):regs[reg];
    if(ignore_address && writes && reg==0xf4)*v=0;
    if(reg==0xf8){
        parity_reads++;
        if((delayed_parity && parity_reads<=3) ||
           (persistent_changed_parity && memory[0x4e9]==0x0c))*v^=0x10;
    }
    return 0;
}
int tuner_write_register(unsigned bank,unsigned reg,uint8_t v){
    if(payload_expected){assert(reg==0xf6);payload_expected=0;}
    assert(bank==0x61 && reg>=0xf3 && reg<=0xf6);ops++;writes++;
    if(reg==0xf3){
        assert(v==0xe0 || v==0xe3);regs[reg]=v==0xe3?0xe1:v;
        if(v==0xe3){cursor=((unsigned)regs[0xf4]<<8)|regs[0xf5];parity=parity_reads=0;}
        if(v==0xe3 && ++halt_writes==2)payload_expected=ops!=fail_at;
    }else if(reg==0xf6){
        assert(cursor>=0x298 && cursor<0x298+1304 && regs[0xf3]==0xe1);
        unsigned offset=cursor-0x298;
        uint8_t correction=(current_operand>>8)^(current_operand&255)^0x0f^0x0d;
        assert(v==(offset==1303?(pseq_bytes[607+offset]^correction):
                   cursor==0x4e8?current_operand>>8:
                   cursor==0x4e9?(current_operand&255):pseq_bytes[607+offset]));
        if(persistent_restore && current_operand==0x0f0d && cursor==0x4e9)return -1;
        memory[cursor++]=v;
        parity^=v;
    }else if(!(ignore_address && reg==0xf4))regs[reg]=v;
    return ops==fail_at?-1:0; /* Write accepted before transport error. */
}
int tuner_write_burst(unsigned bank,unsigned reg,const uint8_t *bytes,unsigned count){
    assert(bank==0x61 && reg==0xf6 && count && count<=128);
    bursts++;
    /* Model partial acceptance inside one transaction, not bus framing. */
    for(unsigned n=0;n<count;n++)if(tuner_write_register(bank,reg,bytes[n]))return -1;
    return 0;
}
static void reset(void){
    memset(regs,0,sizeof regs);regs[0xf3]=0xe0;regs[0xf4]=2;regs[0xf5]=0x98;
    memcpy(memory+0x298,pseq_bytes+607,1304);
    ops=writes=cursor=parity=restore_start=payload_expected=halt_writes=0;output[0]=0;
    bursts=0;
}
int main(void){
    unsigned total=0,before_restore=0;
    for(unsigned fail=0;fail<=total || !fail;fail++){
        reset();fail_at=fail;tuner_program_mailbox_probe();
        if(!fail){total=ops;before_restore=restore_start;
            assert(bursts==22 && strstr(output,"main6d=0000002a"));
            assert(strstr(output,"read-restored-unclassified-reinitialize-required"));}
        else if(fail<before_restore)assert(!strstr(output,"status=read-restored-unclassified"));
        assert(memory[0x4e7]==0xc5 && memory[0x4e8]==0x0f && memory[0x4e9]==0x0d);
        assert(!memcmp(memory+0x298,pseq_bytes+607,1304));
        assert(regs[0xf3]==0xe0 && regs[0xf4]==2 && regs[0xf5]==0x98);
    }
    reset();fail_at=0;source_ok=0;tuner_program_mailbox_probe();
    assert(!writes && strstr(output,"unexpected-source-payload"));source_ok=1;
    uint8_t expected;
    assert(tuner_program_mailbox_write_record(0x0b,&expected)==-1);
    assert(tuner_program_mailbox_write_record(0x0c,0)==-1 && !writes);
    reset();regs[0xf3]=0x23;tuner_program_mailbox_probe();
    assert(!writes && strstr(output,"unexpected-state"));
    reset();ignore_address=1;tuner_program_mailbox_probe();
    assert(memory[0x4e9]==0x0d && strstr(output,"restore-failed-reinitialize-required"));ignore_address=0;
    reset();delayed_parity=1;tuner_program_mailbox_probe();
    assert(strstr(output,"read-restored-unclassified-reinitialize-required"));delayed_parity=0;
    reset();persistent_changed_parity=1;tuner_program_mailbox_probe();
    assert(!strstr(output,"MAILBOX sample phase=00000001"));
    assert(strstr(output,"read-failed-restored-reinitialize-required") && memory[0x4e9]==0x0d);
    persistent_changed_parity=0;
    reset();fail_at=0;uart_index=2;tuner_program_mailbox_select();
    assert(strstr(output,"MAILBOX transfer operand=00000f07"));
    assert(strstr(output,"status=read-restored-unclassified") && memory[0x4e9]==0x0d);
    reset();uart_index=255;tuner_program_mailbox_select();
    assert(!ops && !writes && strstr(output,"unknown-operand"));
    reset();uart_index=-1;ticks=0;tuner_program_mailbox_select();
    assert(!ops && !writes && strstr(output,"operand-transport-timeout"));
    reset();assert(!tuner_program_mailbox_operand(0x1234) && !ops && !writes);
    reset();fail_at=0;tuner_program_mailbox_sweep();
    assert(bursts==13*22 && !memcmp(memory+0x298,pseq_bytes+607,1304));
    assert(strstr(output,"MAILBOX sweep completed=0000000d"));
    assert(strstr(output,"MAILBOX sweep end status=read-restored-unclassified-reinitialize-required"));
    reset();fail_at=40;tuner_program_mailbox_sweep();
    assert(strstr(output,"MAILBOX sweep completed=00000000"));
    assert(strstr(output,"MAILBOX sweep end status=failed-reinitialize-required"));
    assert(!memcmp(memory+0x298,pseq_bytes+607,1304));
    reset();persistent_restore=1;tuner_program_mailbox_probe();
    assert(regs[0xf3]==0xe1 && strstr(output,"restore-failed-reinitialize-required"));
    printf("PASS: mailbox uncertain-write restoration, %u single failure positions, address guard and persistent restore failure\n",total);
}
