/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"
#include "tuner_tmcc.h"
static void field(const char *name,unsigned n){uart_puts(name);uart_hex(n);}
void tuner_tmcc_read(void){
    uint8_t raw[8],again[8],before,after;struct tuner_tmcc_info info;
    uart_puts("TMCC read start\n");
    if(tuner_read_register(0x61,0x97,&before))goto failed;
    for(unsigned attempt=0;attempt<3;attempt++){
        unsigned changed=0;
        for(unsigned n=0;n<8;n++)if(tuner_read_register(0x61,0xa0+n,raw+n))goto failed;
        for(unsigned n=0;n<8;n++){
            if(tuner_read_register(0x61,0xa0+n,again+n))goto failed;
            if(raw[n]!=again[n])changed=1;
        }
        if(!changed)break;
        if(attempt==2){uart_puts("TMCC read end status=unstable\n");return;}
    }
    if(tuner_read_register(0x61,0x97,&after))goto failed;
    field("TMCC sync before=",before);field(" after=",after);uart_puts("\nTMCC raw");
    for(unsigned n=0;n<8;n++)field(" byte=",raw[n]);
    uart_puts("\n");
    tuner_tmcc_decode(raw,&info);
    field("TMCC system=",info.system);field(" countdown=",info.countdown);
    field(" emergency=",info.emergency);field(" partial=",info.partial);field(" phase=",info.phase);uart_puts("\n");
    for(unsigned n=0;n<3;n++){
        field("TMCC layer=",n);field(" modulation=",info.layer[n].modulation);
        field(" code_rate=",info.layer[n].code_rate);field(" interleave=",info.layer[n].interleave);
        field(" segments=",info.layer[n].segments);uart_puts("\n");
    }
    uart_puts(((before&0x18)==0x10 && (after&0x18)==0x10)?
              "TMCC read end status=stable-frame-lock\n":"TMCC read end status=not-locked\n");return;
failed:uart_puts("TMCC read end status=i2c-failed\n");
}
void tuner_band_base(unsigned v){
    uint8_t before,after;
    uart_puts("TUNER band base start\n");
    /* Two evidence-backed presets only. UF1's required precondition remains
     * experimental; this is not an arbitrary register write interface. */
    if(v!=4 && v!=8)goto failed;
    if(tuner_read_register(0x62,4,&before) || tuner_write_register(0x62,4,(uint8_t)v) ||
       tuner_read_register(0x62,4,&after))goto failed;
    field("TUNER band base before=",before);field(" requested=",v);field(" after=",after);uart_puts("\n");
    uart_puts(after==v?"TUNER band base end status=readback\n":"TUNER band base end status=mismatch\n");return;
failed:uart_puts("TUNER band base end status=failed\n");
}
