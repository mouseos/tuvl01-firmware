/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"
#include "time_counts.h"
static int restore(unsigned reg,uint8_t value){
    for(unsigned n=0;n<2;n++){
        uint8_t readback;
        if(!tuner_write_register(0x61,reg,value) &&
           !tuner_read_register(0x61,reg,&readback) && readback==value)return 0;
    }
    return -1;
}
static int samples(unsigned phase,int requested){
    static struct {uint32_t before,after;uint8_t first,data,last;} rows[16];
    for(unsigned n=0;n<16;n++){
        rows[n].before=board_time_counts();
        if(tuner_read_register(0x61,0xd4,&rows[n].first) ||
           tuner_read_register(0x61,0xd5,&rows[n].data) ||
           tuner_read_register(0x61,0xd4,&rows[n].last))return -1;
        rows[n].after=board_time_counts();
        if(requested>=0 && (rows[n].first!=requested || rows[n].last!=requested)){
            uart_puts("D4WIN mismatch requested=");uart_hex(requested);
            uart_puts(" first=");uart_hex(rows[n].first);uart_puts(" last=");uart_hex(rows[n].last);uart_puts("\n");
            return -1;
        }
    }
    for(unsigned n=0;n<16;n++){
        uart_puts("D4WIN sample phase=");uart_hex(phase);uart_puts(" index=");uart_hex(n);
        uart_puts(" first=");uart_hex(rows[n].first);uart_puts(" data=");uart_hex(rows[n].data);
        uart_puts(" last=");uart_hex(rows[n].last);uart_puts(" before=");uart_hex(rows[n].before);
        uart_puts(" after=");uart_hex(rows[n].after);uart_puts("\n");
    }
    return 0;
}
void tuner_d4_window_halted(void){
    uint8_t control,high,low,saved=0,v;unsigned failed=0,restored=1,touched=0;
    uart_puts("D4WIN probe start\n");
    if(tuner_read_register(0x61,0xf3,&control) || tuner_read_register(0x61,0xf4,&high) ||
       tuner_read_register(0x61,0xf5,&low)){
        uart_puts("D4WIN probe end status=read-failed-before-change\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("D4WIN probe end status=unexpected-state\n");return;
    }
    if(samples(0,-1)){uart_puts("D4WIN probe end status=baseline-read-failed\n");return;}
    if(tuner_write_register(0x61,0xf3,0xe3) || tuner_read_register(0x61,0xf3,&v) ||
       (v!=0xe1 && v!=0xe3) || tuner_read_register(0x61,0xd4,&saved))failed=1;
    if(!failed){
        /* Only the stock 05C9..05F5 mask/OR candidates. No arbitrary mode,
         * patch writes or assumed I/Q packing. Save AFTER halting PSEQ. */
        static const uint8_t masks[]={0xd7,0xdf,0xe7},bits[]={0x14,0x1c,0x24};
        uart_puts("D4WIN saved=");uart_hex(saved);uart_puts("\n");
        for(unsigned n=0;n<3;n++){
            uint8_t requested=(saved&masks[n])|bits[n];touched=1;
            uart_puts("D4WIN block phase=");uart_hex(n+1);uart_puts(" requested=");uart_hex(requested);uart_puts("\n");
            if(tuner_write_register(0x61,0xd4,requested) || tuner_read_register(0x61,0xd4,&v)){
                failed=1;break;
            }
            uart_puts("D4WIN readback requested=");uart_hex(requested);uart_puts(" observed=");uart_hex(v);uart_puts("\n");
            if(v!=requested || samples(n+1,requested)){failed=1;break;}
        }
    }
    /* Any uncertain D4 write may have been accepted. Restore before resume;
     * persistent D4 failure leaves PSEQ halted for a complete host reload. */
    if(touched && restore(0xd4,saved))restored=0;
    if(restored && restore(0xf3,control))restored=0;
    if(tuner_read_register(0x61,0xf4,&v) || v!=high)restored=0;
    if(tuner_read_register(0x61,0xf5,&v) || v!=low)restored=0;
    if(restored && samples(4,-1))failed=1;
    uart_puts(!restored?"D4WIN probe end status=restore-failed-reinitialize-required\n":
              failed?"D4WIN probe end status=read-failed-restored-reinitialize-required\n":
                     "D4WIN probe end status=read-restored-unclassified-reinitialize-required\n");
}

/* Keep UART outside successful acquisition blocks. A mismatch row is retained
 * as unselected evidence, then all later selections are skipped. */
static int live_samples(unsigned phase,unsigned selector,int requested){
    static struct {uint32_t before,after;uint8_t first,data,last,selected;} rows[8];
    unsigned complete=0,failed=0;
    for(unsigned n=0;n<8;n++){
        rows[n].before=board_time_counts();
        if(tuner_read_register(0x61,0xd4,&rows[n].first) ||
           tuner_read_register(0x61,0xd5,&rows[n].data) ||
           tuner_read_register(0x61,0xd4,&rows[n].last)){failed=1;break;}
        rows[n].after=board_time_counts();complete++;
        rows[n].selected=requested>=0 && rows[n].first==requested && rows[n].last==requested;
        if(requested>=0 && !rows[n].selected){failed=1;break;}
    }
    for(unsigned n=0;n<complete;n++){
        uart_puts("D4LIVE sample phase=");uart_hex(phase);uart_puts(" index=");uart_hex(n);
        uart_puts(" selector=");uart_hex(selector);uart_puts(" requested=");uart_hex(requested);
        uart_puts(" first=");uart_hex(rows[n].first);uart_puts(" data=");uart_hex(rows[n].data);
        uart_puts(" last=");uart_hex(rows[n].last);uart_puts(" before=");uart_hex(rows[n].before);
        uart_puts(" after=");uart_hex(rows[n].after);uart_puts(" selected=");uart_hex(rows[n].selected);uart_puts("\n");
    }
    return failed?-1:0;
}
void tuner_d4_window_live_buffered(void){
    uint8_t control,high,low,saved,v;unsigned failed=0,restored=1,touched=0;
    uart_puts("D4LIVE probe start\n");
    if(tuner_read_register(0x61,0xf3,&control) || tuner_read_register(0x61,0xf4,&high) ||
       tuner_read_register(0x61,0xf5,&low)){
        uart_puts("D4LIVE probe end status=read-failed-before-change\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){uart_puts("D4LIVE probe end status=unexpected-state\n");return;}
    if(live_samples(0,0,-1) || tuner_read_register(0x61,0xd4,&saved)){
        uart_puts("D4LIVE probe end status=baseline-read-failed\n");return;
    }
    static const uint8_t masks[]={0xcf,0xef,0xf7,0xd7,0xdf,0xe7};
    static const uint8_t bits[]={0x0c,0x2c,0x34,0x14,0x1c,0x24},selectors[]={1,5,6,2,3,4};
    uart_puts("D4LIVE saved=");uart_hex(saved);uart_puts("\n");
    for(unsigned n=0;n<6;n++){
        uint8_t requested=(saved&masks[n])|bits[n];touched=1;
        uart_puts("D4LIVE block phase=");uart_hex(n+1);uart_puts(" selector=");uart_hex(selectors[n]);
        uart_puts(" requested=");uart_hex(requested);uart_puts("\n");
        if(tuner_write_register(0x61,0xd4,requested) || tuner_read_register(0x61,0xd4,&v)){failed=1;break;}
        /* No UART between write/readback and the eight-row buffer. */
        if(v!=requested)failed=1;
        else if(live_samples(n+1,selectors[n],requested))failed=1;
        uart_puts("D4LIVE readback requested=");uart_hex(requested);uart_puts(" observed=");uart_hex(v);uart_puts("\n");
        if(failed)break;
    }
    if(touched && restore(0xd4,saved))restored=0;
    /* PSEQ control/address were read only; verify they stayed unchanged. */
    if(tuner_read_register(0x61,0xf3,&v) || v!=control)restored=0;
    if(tuner_read_register(0x61,0xf4,&v) || v!=high)restored=0;
    if(tuner_read_register(0x61,0xf5,&v) || v!=low)restored=0;
    if(restored && live_samples(7,0,-1))failed=1;
    uart_puts(!restored?"D4LIVE probe end status=restore-failed-reinitialize-required\n":
              failed?"D4LIVE probe end status=read-failed-restored-reinitialize-required\n":
                     "D4LIVE probe end status=read-restored-unclassified-reinitialize-required\n");
}
