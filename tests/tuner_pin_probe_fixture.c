/* SPDX-License-Identifier: MIT
 * gcc -Wall -Wextra -Werror -include tests/pin_probe_board.h -idirafter include
 * tests/tuner_pin_probe_fixture.c src/tuner_pin_probe.c -o pin-probe-test */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "tuner.h"
static uint8_t spcr,e8,f8;
static uint16_t mux,ior,pr;
static uint32_t dma[2];
static unsigned operations,fail_at,samples,mode_changed;
static char end[128];
uint8_t *pin_mock8(uint32_t a){assert(a==0xffff8800U);return &spcr;}
uint16_t *pin_mock16(uint32_t a){
    if(a==0xfffe386cU)return &mux;
    if(a==0xfffe3872U)return &ior;
    assert(a==0xfffe387aU);return &pr;
}
uint32_t *pin_mock32(uint32_t a){
    assert(a==0xfffe100cU || a==0xfffe101cU);return &dma[a==0xfffe101cU];
}
uint32_t board_time_counts(void){
    assert(mux==0 && (ior&0xf0U)==0 && (ior&2U));
    samples++;return samples;
}
void uart_puts(const char *s){if(strstr(s,"PIN capture end status="))snprintf(end,sizeof end,"%s",s);}
void uart_hex(uint32_t v){(void)v;}
int tuner_read_register(unsigned b,unsigned r,uint8_t *v){
    assert(b==0x62 && (r==0xe8 || r==0xf8));
    if(++operations==fail_at)return -1;
    *v=r==0xe8?e8:f8;return 0;
}
int tuner_write_register(unsigned b,unsigned r,uint8_t v){
    assert(b==0x62 && r==0xe8 && (v==0xa0 || v==0xa2));
    assert(mux==0 && !(ior&0xf0));
    if(v==0xa0)mode_changed++;
    e8=v;return ++operations==fail_at?-1:0;
}
static void reset(unsigned failure){
    spcr=8;e8=0xa2;f8=0xb1;mux=0x2222;ior=0x5af2;pr=0x90;
    dma[0]=dma[1]=0;operations=samples=mode_changed=0;fail_at=failure;end[0]=0;
}
int main(void){
    reset(0);tuner_pin_capture_probe();
    assert(samples==1024 && mode_changed==1 && e8==0xa2 && f8==0xb1);
    assert(mux==0x2222 && ior==0x5af2);
    assert(strstr(end,"captured-restored-unclassified"));
    /* Include writes that reached the chip but reported failure. */
    for(unsigned n=1;n<=7;n++){
        reset(n);tuner_pin_capture_probe();assert(e8==0xa2 && f8==0xb1);
        if(strstr(end,"restore-failed-inputs-retained"))assert(mux==0 && ior==0x5a02);
        else assert(mux==0x2222 && ior==0x5af2);
        assert(samples<=1024);
    }
    reset(0);dma[1]=1;tuner_pin_capture_probe();assert(!operations && !samples && mux==0x2222);
    reset(0);spcr=0x48;tuner_pin_capture_probe();assert(!operations && !samples);
    reset(0);mux=0;tuner_pin_capture_probe();assert(!operations && !samples);
    reset(0);e8=0xa1;tuner_pin_capture_probe();assert(operations==2 && !samples && mux==0x2222);
    puts("pin capture restoration and failure cases passed");
}
