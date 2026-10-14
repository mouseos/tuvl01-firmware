/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"
#include "time_counts.h"
void tuner_monitor_window_pause(unsigned milliseconds);

/* Known PSEQ motifs select 84=00/03 before reading BA/BB. Neither the
 * selector meaning nor a coherent I/Q pair is established. Intermediate
 * values 01/02 are hypotheses, not manufacturer-documented modes.
 * No patch writes. */
static int samples(unsigned phase,int requested,unsigned reselect,unsigned buffered,unsigned pause){
    static struct {uint32_t before,after;uint8_t selector,ba,bb;} rows[16];
    for(unsigned n=0;n<16;n++){
        uint8_t selector,bytes[2];unsigned received=0;
        if(buffered && n && pause)tuner_monitor_window_pause(pause);
        if(buffered)rows[n].before=board_time_counts();
        if(reselect==2 && tuner_write_register(0x61,0x84,requested?0:3))return -1;
        if(reselect && tuner_write_register(0x61,0x84,requested))return -1;
        if(tuner_read_register(0x61,0x84,&selector) ||
           (requested>=0 && selector!=requested) ||
           tuner_read_burst_restart(0x61,0xba,bytes,2,&received) || received!=2)return -1;
        if(buffered){
            rows[n].after=board_time_counts();rows[n].selector=selector;
            rows[n].ba=bytes[0];rows[n].bb=bytes[1];continue;
        }
        uart_puts("MONWIN sample phase=");uart_hex(phase);
        uart_puts(" index=");uart_hex(n);uart_puts(" selector=");uart_hex(selector);
        uart_puts(" ba=");uart_hex(bytes[0]);uart_puts(" bb=");uart_hex(bytes[1]);
        uart_puts("\n");
    }
    if(buffered)for(unsigned n=0;n<16;n++){
        uart_puts("MONWIN time phase=");uart_hex(phase);uart_puts(" index=");uart_hex(n);
        uart_puts(" before=");uart_hex(rows[n].before);uart_puts(" after=");uart_hex(rows[n].after);uart_puts("\n");
        uart_puts("MONWIN sample phase=");uart_hex(phase);uart_puts(" index=");uart_hex(n);
        uart_puts(" selector=");uart_hex(rows[n].selector);uart_puts(" ba=");uart_hex(rows[n].ba);
        uart_puts(" bb=");uart_hex(rows[n].bb);uart_puts("\n");
    }
    return 0;
}
static int block(unsigned phase,uint8_t requested,unsigned reselect,unsigned buffered,unsigned pause){
    uint8_t v;
    uart_puts("MONWIN block phase=");uart_hex(phase);
    uart_puts(" requested=");uart_hex(requested);uart_puts(" reselect=");uart_hex(reselect);uart_puts("\n");
    if(buffered){uart_puts("MONWIN buffered phase=");uart_hex(phase);uart_puts(" pause_ms=");uart_hex(pause);uart_puts("\n");}
    if(tuner_write_register(0x61,0x84,requested) ||
       tuner_read_register(0x61,0x84,&v) || v!=requested)return -1;
    return samples(phase,requested,reselect,buffered,pause);
}
static int restore(unsigned reg,uint8_t value){
    for(unsigned n=0;n<2;n++){
        uint8_t v;
        if(!tuner_write_register(0x61,reg,value) &&
           !tuner_read_register(0x61,reg,&v) && v==value)return 0;
    }
    return -1;
}
static void monitor_probe(unsigned updates){
    uint8_t control,high,low,selector,v;unsigned failed=0,restored=1,touched_selector=0;
    uart_puts("MONWIN probe start\n");
    uart_puts("MONWIN updates=");uart_hex(updates);uart_puts("\n");
    if(tuner_read_register(0x61,0xf3,&control) || tuner_read_register(0x61,0xf4,&high) ||
       tuner_read_register(0x61,0xf5,&low) || tuner_read_register(0x61,0x84,&selector)){
        uart_puts("MONWIN probe end status=read-failed-before-change\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("MONWIN probe end status=unexpected-state\n");return;
    }
    if(samples(0,-1,0,updates==2,0)){
        uart_puts("MONWIN probe end status=baseline-read-failed\n");return;
    }
    /* Save selector again after baseline: the running PSEQ can change it. */
    if(tuner_write_register(0x61,0xf3,0xe3) ||
       tuner_read_register(0x61,0xf3,&v) || (v!=0xe1 && v!=0xe3) ||
       tuner_read_register(0x61,0x84,&selector))failed=1;
    if(!failed && updates!=2){
        for(unsigned n=0;n<4;n++){
            touched_selector=1;
            if(block(n+1,n,0,0,0)){
                failed=1;break;
            }
        }
    }
    if(updates==1 && !failed){
        /* Rewrites and edges of observed 00..03 precede unverified 04..07.
         * No manufacturer field width or trigger semantics are assumed. */
        for(unsigned rule=1;rule<=2 && !failed;rule++)
            for(unsigned mode=0;mode<4;mode++)
                if(block(1+4*rule+mode,mode,rule,0,0)){failed=1;break;}
        for(unsigned mode=4;mode<8 && !failed;mode++)
            if(block(9+mode,mode,0,0,0))failed=1;
    }
    if(updates==2 && !failed)for(unsigned n=0;n<6;n++){
        touched_selector=1;
        /* Equal read counts with no UART inside acquisition; compare held
         * selectors, ten milliseconds between reads, and repeated writes. */
        if(block(n+1,n<3?1:4,n%3==2,1,n%3==1?10:0)){failed=1;break;}
    }
    /* Any uncertain write may have been accepted. Restore selector before
     * resuming. Persistent selector failure leaves PSEQ halted for reload. */
    if(touched_selector && restore(0x84,selector))restored=0;
    if(restored && restore(0xf3,control))restored=0;
    if(tuner_read_register(0x61,0xf4,&v) || v!=high)restored=0;
    if(tuner_read_register(0x61,0xf5,&v) || v!=low)restored=0;
    if(restored && samples(updates==2?7:updates?17:5,-1,0,updates==2,0))failed=1;
    uart_puts(!restored?"MONWIN probe end status=restore-failed-reinitialize-required\n":
              failed?"MONWIN probe end status=read-failed-restored-reinitialize-required\n":
                     "MONWIN probe end status=read-restored-unclassified-reinitialize-required\n");
}
void tuner_monitor_window_probe(void){monitor_probe(0);}
void tuner_monitor_window_updates(void){monitor_probe(1);}
void tuner_monitor_window_timing(void){monitor_probe(2);}
