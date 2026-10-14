#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t regs[256];
static unsigned ops,fail_at,writes,times,acquiring,ignore_selection,persistent_restore,race,ignore_restore;
static char output[65536];
static int uart_index=-1;static uint32_t ticks;
int uart_getc(void){int value=uart_index;uart_index=-1;return value;}
uint32_t xTaskGetTickCount(void){return ticks;}
void vTaskDelay(uint32_t n){ticks+=n;}
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
    assert(value==0x0e || value==0x2e || value==0x36 || value==0x16 || value==0x1e || value==0x26 || value==0x06 || value==0x3e || value==2);
    if(persistent_restore && writes>1 && value==0x1e)return -1;
    if((!ignore_selection || value==0x1e) && !(ignore_restore && writes>1 && value==0x1e))regs[reg]=value;
    return ops==fail_at?-1:0; /* Accepted before an uncertain error. */
}
static void reset(void){
    memset(regs,0,sizeof regs);regs[0xd4]=0x1e;regs[0xf3]=0xe0;regs[0xf4]=2;regs[0xf5]=0x98;
    ops=writes=times=acquiring=0;output[0]=0;ticks=0;uart_index=-1;
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
    for(unsigned index=0;index<6;index++){
        unsigned single_total=0;
        for(unsigned fail=0;!fail || fail<=single_total;fail++){
            reset();fail_at=fail;tuner_d4_window_live_selected(index);
            if(!fail){single_total=ops;assert(times==48 && writes==2);
                assert(strstr(output,"read-restored-unclassified-reinitialize-required"));}
            assert(regs[0xd4]==0x1e && regs[0xf3]==0xe0 && regs[0xf4]==2 && regs[0xf5]==0x98);
        }
        printf("PASS: individual D4 selector index%u, %u uncertain failures,24 rows/full restore\n",index,single_total);
    }
    reset();fail_at=0;tuner_d4_window_live_selected(6);assert(!writes && !ops);
    reset();uart_index=255;tuner_d4_window_live_select();assert(!writes && !ops && strstr(output,"unknown-selector"));
    reset();tuner_d4_window_live_select();assert(!writes && !ops && ticks==2000 && strstr(output,"selector-transport-timeout"));
    reset();uart_index=3;tuner_d4_window_live_select();assert(writes==2 && times==48 && strstr(output,"selector=00000002"));
    for(unsigned index=0;index<2;index++){
        unsigned single_total=0;
        for(unsigned fail=0;!fail || fail<=single_total;fail++){
            reset();fail_at=fail;tuner_d4_window_live_experimental(index);
            if(!fail){single_total=ops;assert(times==48 && writes==2);
                assert(strstr(output,"provenance=experimental-field-encoding"));
                assert(strstr(output,index?"requested=0000003e":"requested=00000006"));}
            assert(regs[0xd4]==0x1e && regs[0xf3]==0xe0 && regs[0xf4]==2 && regs[0xf5]==0x98);
        }
        printf("PASS: experimental index%u, %u uncertain failures/full restore\n",index,single_total);
    }
    reset();fail_at=0;uart_index=2;tuner_d4_window_experimental_select();assert(!ops && !writes);
    reset();uart_index=1;tuner_d4_window_experimental_select();assert(writes==2 && times==48 && strstr(output,"selector=00000007"));
    reset();ignore_selection=1;tuner_d4_window_live_experimental(0);
    assert(strstr(output,"read-failed-restored") && regs[0xd4]==0x1e);ignore_selection=0;
    reset();race=1;tuner_d4_window_live_experimental(1);
    assert(strstr(output,"selected=00000000") && strstr(output,"read-failed-restored") && regs[0xd4]==0x1e);race=0;
    unsigned operand_total=0;
    for(unsigned fail=0;!fail || fail<=operand_total;fail++){
        reset();fail_at=fail;tuner_d4_window_live_operand02();
        if(!fail){operand_total=ops;assert(times==48 && writes==2);
            assert(strstr(output,"provenance=native-067E-operand02-candidate"));
            assert(strstr(output,"phase=00000009 index=00000007 selector=00000000 requested=00000002"));
            assert(strstr(output,"restore attempt=00000000 requested=0000001e write_ok=00000001 read_ok=00000001 observed=0000001e"));}
        assert(regs[0xd4]==0x1e && regs[0xf3]==0xe0 && regs[0xf4]==2 && regs[0xf5]==0x98);
    }
    reset();fail_at=0;ignore_selection=1;tuner_d4_window_live_operand02();
    assert(strstr(output,"requested=00000002 observed=0000001e") && strstr(output,"read-failed-restored"));ignore_selection=0;
    reset();persistent_restore=1;tuner_d4_window_live_operand02();
    assert(strstr(output,"restore attempt=00000001 requested=0000001e write_ok=00000000 read_ok=00000000 observed=ffffffff"));
    assert(strstr(output,"restore-failed-reinitialize-required"));persistent_restore=0;
    reset();ignore_restore=1;tuner_d4_window_live_operand02();
    assert(strstr(output,"restore attempt=00000001 requested=0000001e write_ok=00000001 read_ok=00000001 observed=00000002"));
    assert(strstr(output,"restore-failed-reinitialize-required") && regs[0xd4]==2);ignore_restore=0;
    printf("PASS: native operand02, %u uncertain failures/24 rows; buffered restore evidence\n",operand_total);

}
