/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"

/* Known PSEQ motifs select 84=00/03 before reading BA/BB. Neither the
 * selector meaning nor a coherent I/Q pair is established. No patch writes. */
static int samples(unsigned phase){
    for(unsigned n=0;n<16;n++){
        uint8_t selector,bytes[2];unsigned received=0;
        if(tuner_read_register(0x61,0x84,&selector) ||
           tuner_read_burst_restart(0x61,0xba,bytes,2,&received) || received!=2)return -1;
        uart_puts("MONWIN sample phase=");uart_hex(phase);
        uart_puts(" index=");uart_hex(n);uart_puts(" selector=");uart_hex(selector);
        uart_puts(" ba=");uart_hex(bytes[0]);uart_puts(" bb=");uart_hex(bytes[1]);
        uart_puts("\n");
    }
    return 0;
}
static int restore(unsigned reg,uint8_t value){
    for(unsigned n=0;n<2;n++){
        uint8_t v;
        if(!tuner_write_register(0x61,reg,value) &&
           !tuner_read_register(0x61,reg,&v) && v==value)return 0;
    }
    return -1;
}
void tuner_monitor_window_probe(void){
    uint8_t control,high,low,selector,v;unsigned failed=0,restored=1,touched_selector=0;
    uart_puts("MONWIN probe start\n");
    if(tuner_read_register(0x61,0xf3,&control) || tuner_read_register(0x61,0xf4,&high) ||
       tuner_read_register(0x61,0xf5,&low) || tuner_read_register(0x61,0x84,&selector)){
        uart_puts("MONWIN probe end status=read-failed-before-change\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("MONWIN probe end status=unexpected-state\n");return;
    }
    if(samples(0)){
        uart_puts("MONWIN probe end status=baseline-read-failed\n");return;
    }
    /* Save selector again after baseline: the running PSEQ can change it. */
    if(tuner_write_register(0x61,0xf3,0xe3) ||
       tuner_read_register(0x61,0xf3,&v) || (v!=0xe1 && v!=0xe3) ||
       tuner_read_register(0x61,0x84,&selector))failed=1;
    if(!failed){
        const uint8_t modes[2]={0,3};
        for(unsigned n=0;n<2;n++){
            touched_selector=1;
            if(tuner_write_register(0x61,0x84,modes[n]) ||
               tuner_read_register(0x61,0x84,&v) || v!=modes[n] || samples(n+1)){
                failed=1;break;
            }
        }
    }
    /* Any uncertain write may have been accepted. Restore selector before
     * resuming. Persistent selector failure leaves PSEQ halted for reload. */
    if(touched_selector && restore(0x84,selector))restored=0;
    if(restored && restore(0xf3,control))restored=0;
    if(tuner_read_register(0x61,0xf4,&v) || v!=high)restored=0;
    if(tuner_read_register(0x61,0xf5,&v) || v!=low)restored=0;
    if(restored && samples(3))failed=1;
    uart_puts(!restored?"MONWIN probe end status=restore-failed-reinitialize-required\n":
              failed?"MONWIN probe end status=read-failed-restored-reinitialize-required\n":
                     "MONWIN probe end status=read-restored-unclassified-reinitialize-required\n");
}
