/* Host: gcc -Wall -Wextra -Werror -idirafter include
 * tests/tuner_program_probe_fixture.c src/tuner_program_probe.c -o probe-test */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t registers[256];
static unsigned operations,fail_at,writes;
static char output[2048];
void uart_puts(const char *s){strcat(output,s);}
void uart_hex(uint32_t v){char b[9];snprintf(b,sizeof b,"%08x",v);strcat(output,b);}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t *v){
    assert(bank==0x61);operations++;
    if(operations==fail_at)return -1;
    *v=registers[reg];return 0;
}
int tuner_write_register(unsigned bank,unsigned reg,uint8_t v){
    assert(bank==0x61 && reg==0xf3 && (v==0xe0 || v==0xe3));
    operations++;writes++;
    /* Model a write that reached the chip but reported a transport failure. */
    registers[reg]=v;return operations==fail_at?-1:0;
}
int main(void){
    for(unsigned fail=0;fail<=24;fail++){
        memset(registers,0,sizeof registers);registers[0xf3]=0xe0;
        registers[0xf4]=2;registers[0xf5]=0x98;
        operations=writes=0;fail_at=fail;output[0]=0;
        tuner_program_port_probe();
        assert(registers[0xf3]==0xe0);
        assert(registers[0xf4]==2 && registers[0xf5]==0x98);
        if(fail>=1 && fail<=3)assert(writes==0);else assert(writes==2);
        assert(strstr(output,"PROGRAM probe end status="));
        if(fail==0)assert(strstr(output,"read-restored-unclassified"));
        else if(fail<=3)assert(strstr(output,"i2c-failed-before-change"));
        else if(fail<=20)assert(strstr(output,"read-failed-restored"));
        else assert(strstr(output,"restore-failed"));
    }
    registers[0xf3]=0x23;operations=writes=fail_at=0;output[0]=0;
    tuner_program_port_probe();assert(writes==0 && registers[0xf3]==0x23);
    assert(strstr(output,"unexpected-state"));
    registers[0xf3]=0xe0;registers[0xf5]=0;operations=writes=fail_at=0;output[0]=0;
    tuner_program_port_probe();assert(writes==0 && registers[0xf3]==0xe0);
    assert(strstr(output,"unexpected-state"));
    puts("PASS: finite reads, state guard, restore including uncertain write failure; no payload/address writes");
}
