/* Host: gcc -Wall -Wextra -Werror -idirafter include
 * tests/tuner_program_probe_fixture.c src/tuner_program_probe.c -o probe-test */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t registers[256];
static unsigned operations,fail_at,writes;
static unsigned burst_short,burst_mismatch,ignore_e2,ignore_e3;
static uint8_t write_values[8];
static char output[8192];
void uart_puts(const char *s){strcat(output,s);}
void uart_hex(uint32_t v){char b[9];snprintf(b,sizeof b,"%08x",v);strcat(output,b);}
int tuner_read_register(unsigned bank,unsigned reg,uint8_t *v){
    assert(bank==0x61);operations++;
    if(operations==fail_at)return -1;
    *v=registers[reg];return 0;
}
int tuner_write_register(unsigned bank,unsigned reg,uint8_t v){
    assert(bank==0x61 && reg==0xf3 && (v==0xe0 || v==0xe2 || v==0xe3));
    operations++;assert(writes<8);write_values[writes++]=v;
    /* Model a write that reached the chip but reported a transport failure. */
    registers[reg]=(ignore_e2 && v==0xe2)?(ignore_e2==1?0xe0:0xe1):v;
    if(ignore_e3 && v==0xe3)registers[reg]=ignore_e3==1?0xe1:0xe0;
    return operations==fail_at?-1:0;
}
int tuner_read_burst(unsigned bank,unsigned reg,uint8_t *bytes,unsigned count,unsigned *received){
    assert(bank==0x61 && count<=8);operations++;*received=0;
    if(operations==fail_at)return -1;
    for(unsigned n=0;n<count-burst_short;n++){bytes[n]=registers[(reg+n)&255];*received=n+1;}
    if(burst_mismatch)bytes[0]^=1;
    return 0;
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
    /* Validate every I/O failure in the separate burst diagnostic. */
    unsigned burst_operations=0;
    for(unsigned fail=0;fail<=burst_operations || fail==0;fail++){
        memset(registers,0,sizeof registers);registers[0xf3]=0xe0;
        registers[0xf4]=2;registers[0xf5]=0x98;
        operations=writes=0;fail_at=fail;output[0]=0;
        tuner_program_burst_probe();
        if(fail==0){burst_operations=operations;assert(strstr(output,"read-restored-unclassified"));}
        assert(registers[0xf3]==0xe0 && registers[0xf4]==2 && registers[0xf5]==0x98);
        assert(writes==0 || writes==2);
        assert(strstr(output,"PROGRAM burst end status="));
    }
    registers[0xf3]=0xe0;registers[0xf5]=0;operations=writes=fail_at=0;output[0]=0;
    tuner_program_port_probe();assert(writes==0 && registers[0xf3]==0xe0);
    assert(strstr(output,"unexpected-state"));
    for(unsigned fault=0;fault<2;fault++){
        registers[0xf3]=0xe0;registers[0xf4]=2;registers[0xf5]=0x98;
        operations=writes=fail_at=0;output[0]=0;
        burst_short=fault==0;burst_mismatch=fault==1;
        tuner_program_burst_probe();
        assert(writes==0 && registers[0xf3]==0xe0);
        assert(strstr(output,fault?"validation-mismatch":"validation-burst-failed"));
        operations=writes=fail_at=0;output[0]=0;
        tuner_program_release_probe();
        assert(writes==0 && registers[0xf3]==0xe0);
        assert(strstr(output,fault?"validation-mismatch":"validation-burst-failed"));
    }
    burst_short=burst_mismatch=0;
    registers[0xf3]=0x23;operations=writes=fail_at=0;output[0]=0;
    tuner_program_release_probe();
    assert(writes==0 && registers[0xf3]==0x23 && strstr(output,"unexpected-state"));
    unsigned release_operations=0;
    for(unsigned fail=0;fail<=release_operations || fail==0;fail++){
        memset(registers,0,sizeof registers);registers[0xf3]=0xe0;registers[0xf4]=2;registers[0xf5]=0x98;
        operations=writes=0;fail_at=fail;output[0]=0;
        tuner_program_release_probe();
        if(!fail){release_operations=operations;assert(strstr(output,"read-restored-unclassified"));
            assert(strstr(output,"mode=000000e2 observed=000000e2 type=single") && strstr(output,"mode=000000e2 observed=000000e2 type=burst"));
            assert(writes==4 && write_values[0]==0xe3 && write_values[1]==0xe3 && write_values[2]==0xe2 && write_values[3]==0xe0);}
        assert(registers[0xf3]==0xe0 && registers[0xf4]==2 && registers[0xf5]==0x98);
        assert(writes<=4 && strstr(output,"PROGRAM release end status="));
    }
    ignore_e2=1;operations=writes=fail_at=0;output[0]=0;
    tuner_program_release_probe();
    assert(registers[0xf3]==0xe0 && writes==4);
    assert(strstr(output,"requested=000000e2 observed=000000e0"));
    assert(strstr(output,"mode=000000e2 observed=000000e0 type=single port=000000f6 count=00000008"));
    assert(strstr(output,"read-restored-unclassified"));
    ignore_e2=2;operations=writes=fail_at=0;output[0]=0;
    tuner_program_release_probe();
    assert(registers[0xf3]==0xe0 && writes==4);
    assert(strstr(output,"mode=000000e2 observed=000000e1 type=single port=000000f6 count=00000000"));
    assert(strstr(output,"read-failed-restored"));
    ignore_e2=1;ignore_e3=1;operations=writes=fail_at=0;output[0]=0;
    tuner_program_release_probe();
    assert(registers[0xf3]==0xe0 && writes==4);
    assert(strstr(output,"mode=000000e3 observed=000000e1 type=single port=000000f6 count=00000008"));
    assert(strstr(output,"read-restored-unclassified"));
    ignore_e3=2;operations=writes=fail_at=0;output[0]=0;
    tuner_program_release_probe();
    assert(registers[0xf3]==0xe0 && writes==2);
    assert(strstr(output,"mode=000000e3 observed=000000e0 type=single port=000000f6 count=00000000"));
    assert(strstr(output,"read-failed-restored"));
    printf("PASS: finite reads, guards, uncertain-write restoration; release probe %u I/O failure positions; no payload/address writes\n",release_operations);
}
