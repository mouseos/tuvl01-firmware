/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"

/* Finite experiment at the known last PSEQ patch address. E3 is the stock
 * patch-transfer state, E0 the stock released state. Its READ semantics are
 * unknown: these bytes must not be labelled IQ or program memory yet. */
void tuner_program_port_probe(void){
    const unsigned bank=0x61;
    uint8_t control,high,low,after,bytes[2][8];
    unsigned counts[2]={0,0},failed=0;
    uart_puts("PROGRAM probe start bank=00000061\n");
    if(tuner_read_register(bank,0xf3,&control) ||
       tuner_read_register(bank,0xf4,&high) || tuner_read_register(bank,0xf5,&low)){
        uart_puts("PROGRAM probe end status=i2c-failed-before-change\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("PROGRAM probe end status=unexpected-state\n");return;
    }
    /* Even a failed write might have reached the chip: always restore. */
    if(tuner_write_register(bank,0xf3,0xe3))failed=1;
    if(!failed){
        for(unsigned port=0;port<2 && !failed;port++){
            for(unsigned n=0;n<8;n++){
                if(tuner_read_register(bank,0xf6+port,&bytes[port][n])){failed=1;break;}
                counts[port]++;
            }
        }
    }
    unsigned restored=!tuner_write_register(bank,0xf3,control);
    if(restored && (tuner_read_register(bank,0xf3,&after) || after!=control))restored=0;
    if(restored && (tuner_read_register(bank,0xf4,&after) || after!=high))restored=0;
    if(restored && (tuner_read_register(bank,0xf5,&after) || after!=low))restored=0;
    for(unsigned port=0;port<2;port++){
        uart_puts("PROGRAM port=");uart_hex(0xf6+port);
        uart_puts(" count=");uart_hex(counts[port]);uart_puts(" bytes=");
        for(unsigned n=0;n<counts[port];n++){uart_hex(bytes[port][n]);uart_puts(" ");}
        uart_puts("\n");
    }
    if(!restored)uart_puts("PROGRAM probe end status=restore-failed\n");
    else if(failed)uart_puts("PROGRAM probe end status=read-failed-restored\n");
    else uart_puts("PROGRAM probe end status=read-restored-unclassified\n");
}

void tuner_program_burst_probe(void){
    const unsigned bank=0x61;
    uint8_t control,high,low,after,single[6],ordinary[6],bytes[2][2][8];
    unsigned actual=0,counts[2][2]={{0,0},{0,0}},failed=0,changed=0;
    uart_puts("PROGRAM burst start bank=00000061\n");
    if(tuner_read_register(bank,0xf3,&control) ||
       tuner_read_register(bank,0xf4,&high) || tuner_read_register(bank,0xf5,&low)){
        uart_puts("PROGRAM burst end status=i2c-failed-before-change\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("PROGRAM burst end status=unexpected-state\n");return;
    }
    /* Known cfg_tsout registers: establish transfer length and byte order
     * against independent single-register reads before any mode change. */
    for(unsigned n=0;n<6;n++){
        ordinary[n]=0xa5;
        if(tuner_read_register(bank,0xd6+n,&single[n])){
            uart_puts("PROGRAM burst end status=validation-read-failed\n");return;
        }
    }
    if(tuner_read_burst(bank,0xd6,ordinary,6,&actual) || actual!=6){
        uart_puts("PROGRAM burst end status=validation-burst-failed\n");return;
    }
    for(unsigned n=0;n<6;n++){
        if(ordinary[n]!=single[n]){
            uart_puts("PROGRAM burst end status=validation-mismatch\n");return;
        }
    }
    uart_puts("PROGRAM burst ordinary=verified bytes=");
    for(unsigned n=0;n<6;n++){uart_hex(ordinary[n]);uart_puts(" ");}
    uart_puts("\n");
    for(unsigned mode=0;mode<2 && !failed;mode++){
        if(mode){
            changed=1;
            if(tuner_write_register(bank,0xf3,0xe3)){failed=1;break;}
        }
        for(unsigned port=0;port<2;port++){
            for(unsigned n=0;n<8;n++)bytes[mode][port][n]=0xa5;
            if(tuner_read_burst(bank,0xf6+port,bytes[mode][port],8,&counts[mode][port])){failed=1;break;}
            if(counts[mode][port]!=8){failed=1;break;}
        }
    }
    unsigned restored=1;
    if(changed)restored=!tuner_write_register(bank,0xf3,control);
    if(restored && (tuner_read_register(bank,0xf3,&after) || after!=control))restored=0;
    if(restored && (tuner_read_register(bank,0xf4,&after) || after!=high))restored=0;
    if(restored && (tuner_read_register(bank,0xf5,&after) || after!=low))restored=0;
    for(unsigned mode=0;mode<2;mode++)for(unsigned port=0;port<2;port++){
        uart_puts("PROGRAM burst mode=");uart_hex(mode?0xe3:0xe0);
        uart_puts(" port=");uart_hex(0xf6+port);
        uart_puts(" count=");uart_hex(counts[mode][port]);uart_puts(" bytes=");
        for(unsigned n=0;n<counts[mode][port] && n<8;n++){uart_hex(bytes[mode][port][n]);uart_puts(" ");}
        uart_puts("\n");
    }
    if(!restored)uart_puts("PROGRAM burst end status=restore-failed\n");
    else if(failed)uart_puts("PROGRAM burst end status=read-failed-restored\n");
    else uart_puts("PROGRAM burst end status=read-restored-unclassified\n");
}
