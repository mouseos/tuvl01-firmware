/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t spcr,regs[3][256],before[3][256];
static uint16_t mux,ior,pr;
static uint32_t dma[2];
static unsigned operations,fail_at,bad_at,samples,changing,keep_unrelated;
static char end[128];
uint8_t *pin_mock8(uint32_t a){assert(a==0xffff8800U);return &spcr;}
uint16_t *pin_mock16(uint32_t a){
    if(a==0xfffe386cU)return &mux;
    if(a==0xfffe3872U)return &ior;
    assert(a==0xfffe387aU);return &pr;
}
uint32_t *pin_mock32(uint32_t a){assert(a==0xfffe100cU || a==0xfffe101cU);return &dma[a==0xfffe101cU];}
uint32_t board_time_counts(void){
    assert(mux==0 && !(ior&0xf0U) && (ior&2U));
    assert((regs[2][0xe8]&15)==0 && (regs[2][0xf8]&15)==0 && (regs[0][0xac]&4));
    assert((regs[1][0xd7]&0x70)==0x70 && (regs[1][0xda]&0x38)==8);
    assert(!regs[1][0xdc] && !(regs[1][0xdd]&15));
    assert((regs[1][0xe7]&0x71)==(samples<512?0x31:0x21));
    assert(regs[1][0xdb]==(samples<512?0:0xf9));
    if(keep_unrelated)regs[1][0xe7]|=0x80;
    samples++;return samples;
}
void uart_puts(const char *s){if(strstr(s,"PINTST capture end status="))snprintf(end,sizeof end,"%s",s);}
void uart_hex(uint32_t v){(void)v;}
int tuner_read_register(unsigned b,unsigned r,uint8_t *v){
    assert(b>=0x60 && b<=0x62 && r<256);
    if(++operations==fail_at)return -1;
    *v=regs[b-0x60][r];if(operations==bad_at)*v^=1;
    return 0;
}
int tuner_write_register(unsigned b,unsigned r,uint8_t v){
    assert(mux==0 && !(ior&0xf0U));changing++;
    assert((b==0x62 && (r==0xe8 || r==0xf8)) || (b==0x60 && r==0xac) ||
           (b==0x61 && (r==0xd7 || r==0xda || r==0xdb || r==0xdc || r==0xdd || r==0xe7)));
    regs[b-0x60][r]=v;return ++operations==fail_at?-1:0;
}
static void reset(void){
    memset(regs,0,sizeof regs);regs[2][0xe8]=0xa2;regs[2][0xf8]=0xb1;
    regs[0][0xac]=0x80;regs[1][0xd7]=0x8c;regs[1][0xda]=0xc0;
    regs[1][0xdc]=1;regs[1][0xdd]=0xf3;regs[2][0xf2]=4;regs[1][0xed]=0x16;
    memcpy(before,regs,sizeof regs);spcr=8;mux=0x2222;ior=0x5af2;pr=0x90;
    dma[0]=dma[1]=operations=fail_at=bad_at=samples=changing=keep_unrelated=0;end[0]=0;
}
int main(void){
    reset();tuner_pin_test_probe();unsigned total=operations;
    assert(total==71 && samples==1024 && mux==0x2222 && ior==0x5af2);
    assert(strstr(end,"captured-restored-unclassified") && !memcmp(regs,before,sizeof regs));
    for(unsigned n=1;n<=total;n++){
        reset();fail_at=n;tuner_pin_test_probe();assert(samples<=1024);
        if(strstr(end,"restore-failed-inputs-retained"))assert(mux==0 && ior==0x5a02);
        else {assert(mux==0x2222 && ior==0x5af2);assert(!memcmp(regs,before,sizeof regs));}
    }
    reset();bad_at=38;tuner_pin_test_probe();assert(!samples && strstr(end,"capture-failed-restored"));
    assert(!memcmp(regs,before,sizeof regs));
    reset();keep_unrelated=1;tuner_pin_test_probe();assert(regs[1][0xe7]==0x80 && mux==0x2222);
    reset();regs[1][0xed]=0x56;tuner_pin_test_probe();assert(!changing && strstr(end,"unexpected-tuner-state"));
    reset();regs[1][0xe7]=0x21;tuner_pin_test_probe();assert(!changing && strstr(end,"unexpected-tuner-state"));
    reset();dma[0]=1;tuner_pin_test_probe();assert(!operations);
    puts("pin test: 71 I/O failure positions, uncertain writes, mismatch and masked restoration passed");
}
