/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"

/* Address-dependence experiment, not an established memory reader. Only
 * known Main1 patch-space addresses are selected; no F6 payload/reset writes.
 * E3 is the stock transfer state. Always attempt all restoration writes,
 * including when a failed transaction may already have reached the chip. */
void tuner_program_address_probe(void){
    static const unsigned addresses[]={0,1,0x100,0x101,0x298,0x299};
    uint8_t control,high,low,value,bytes[2];
    unsigned failed=0,changed=0;
    uart_puts("PROGRAM address start bank=00000061\n");
    if(tuner_read_register(0x61,0xf3,&control) ||
       tuner_read_register(0x61,0xf4,&high) || tuner_read_register(0x61,0xf5,&low)){
        uart_puts("PROGRAM address end status=i2c-failed-before-change\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("PROGRAM address end status=unexpected-state\n");return;
    }
    for(unsigned mode=0;mode<2 && !failed;mode++){
        changed=1;
        if(tuner_write_register(0x61,0xf3,mode?0xe3:0xe0)) {failed=1;break;}
        if(tuner_read_register(0x61,0xf3,&value) ||
           (mode?(value!=0xe3 && value!=0xe1):value!=control)){failed=1;break;}
        for(unsigned a=0;a<sizeof addresses/sizeof addresses[0] && !failed;a++){
            unsigned address=addresses[a];
            if(tuner_write_register(0x61,0xf4,address>>8) ||
               tuner_write_register(0x61,0xf5,address&255) ||
               tuner_read_register(0x61,0xf4,&value) || value!=(address>>8) ||
               tuner_read_register(0x61,0xf5,&value) || value!=(address&255)){
                failed=1;break;
            }
            uart_puts("PROGRAM address mode=");uart_hex(mode?0xe3:0xe0);
            uart_puts(" address=");uart_hex(address);uart_puts(" singles=");
            for(unsigned port=0;port<2 && !failed;port++)for(unsigned n=0;n<4;n++){
                if(tuner_read_register(0x61,0xf6+port,&value)){failed=1;break;}
                uart_hex(value);uart_puts(" ");
            }
            unsigned actual=0;
            if(!failed && (tuner_read_burst_restart(0x61,0xf6,bytes,2,&actual) || actual!=2))failed=1;
            uart_puts(" restart=");
            for(unsigned n=0;n<actual && n<2;n++){uart_hex(bytes[n]);uart_puts(" ");}
            uart_puts("\n");
        }
    }
    unsigned restored=1;
    if(changed){
        if(tuner_write_register(0x61,0xf3,0xe3))restored=0;
        if(tuner_write_register(0x61,0xf4,high))restored=0;
        if(tuner_write_register(0x61,0xf5,low))restored=0;
        if(tuner_write_register(0x61,0xf3,control))restored=0;
    }
    if(tuner_read_register(0x61,0xf3,&value) || value!=control)restored=0;
    if(tuner_read_register(0x61,0xf4,&value) || value!=high)restored=0;
    if(tuner_read_register(0x61,0xf5,&value) || value!=low)restored=0;
    uart_puts(!restored?"PROGRAM address end status=restore-failed\n":
              failed?"PROGRAM address end status=read-failed-restored\n":
                     "PROGRAM address end status=read-restored-unclassified\n");
}

/* Compare bus framing without changing the program window or its address.
 * A successful transport is not proof of readable internal sample memory. */
void tuner_program_restart_probe(void){
    uint8_t control,high,low,after,single[6],bytes[8];
    unsigned actual,failed=0;
    uart_puts("PROGRAM restart start bank=00000061\n");
    if(tuner_read_register(0x61,0xf3,&control) ||
       tuner_read_register(0x61,0xf4,&high) || tuner_read_register(0x61,0xf5,&low)){
        uart_puts("PROGRAM restart end status=i2c-failed-before-read\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("PROGRAM restart end status=unexpected-state\n");return;
    }
    for(unsigned n=0;n<6;n++)if(tuner_read_register(0x61,0xd6+n,&single[n])){
        uart_puts("PROGRAM restart end status=validation-read-failed\n");return;
    }
    for(unsigned restart=0;restart<2;restart++){
        actual=0;
        for(unsigned n=0;n<8;n++)bytes[n]=0xa5;
        int result=restart?tuner_read_burst_restart(0x61,0xd6,bytes,6,&actual):
                           tuner_read_burst(0x61,0xd6,bytes,6,&actual);
        if(result || actual!=6)failed=1;
        if(!failed)for(unsigned n=0;n<6;n++)if(bytes[n]!=single[n])failed=1;
        uart_puts("PROGRAM restart validation mode=");uart_hex(restart);
        uart_puts(" count=");uart_hex(actual);uart_puts(" bytes=");
        for(unsigned n=0;n<actual;n++){uart_hex(bytes[n]);uart_puts(" ");}
        uart_puts(failed?" status=failed\n":" status=verified\n");
        if(failed)break;
    }
    if(!failed)for(unsigned port=0;port<2 && !failed;port++){
        for(unsigned restart=0;restart<2;restart++){
            actual=0;
            for(unsigned n=0;n<8;n++)bytes[n]=0xa5;
            int result=restart?tuner_read_burst_restart(0x61,0xf6+port,bytes,8,&actual):
                               tuner_read_burst(0x61,0xf6+port,bytes,8,&actual);
            uart_puts("PROGRAM restart port=");uart_hex(0xf6+port);
            uart_puts(" mode=");uart_hex(restart);uart_puts(" count=");uart_hex(actual);
            uart_puts(" bytes=");
            for(unsigned n=0;n<actual;n++){uart_hex(bytes[n]);uart_puts(" ");}
            uart_puts("\n");
            if(result || actual!=8){failed=1;break;}
        }
    }
    unsigned unchanged=1;
    if(tuner_read_register(0x61,0xf3,&after) || after!=control)unchanged=0;
    if(tuner_read_register(0x61,0xf4,&after) || after!=high)unchanged=0;
    if(tuner_read_register(0x61,0xf5,&after) || after!=low)unchanged=0;
    uart_puts(!unchanged?"PROGRAM restart end status=state-changed\n":
              failed?"PROGRAM restart end status=read-failed-state-unchanged\n":
                     "PROGRAM restart end status=read-state-unchanged-unclassified\n");
}

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

/* The same-family manufacturer's release routine sets F3 bit1 then clears
 * bit0. With the observed upper bits this is E2, unlike TUVL01's E0. Compare
 * E0, transfer E3, then the manufacturer's E3->E2 release, without writing
 * address/data/reset registers. Read semantics remain unclassified. */
void tuner_program_release_probe(void){
    static const uint8_t modes[3]={0xe0,0xe3,0xe2};
    uint8_t observed[3]={0,0,0};
    uint8_t original,high,low,after,ordinary[6],single[6];
    uint8_t data[3][2][2][8];
    unsigned count[3][2][2]={{{0}}},failed=0,changed=0,actual=0;
    const unsigned bank=0x61;
    uart_puts("PROGRAM release start bank=00000061\n");
    if(tuner_read_register(bank,0xf3,&original) || tuner_read_register(bank,0xf4,&high) ||
       tuner_read_register(bank,0xf5,&low)){
        uart_puts("PROGRAM release end status=i2c-failed-before-change\n");return;
    }
    if(original!=0xe0 || high!=2 || low!=0x98){
        uart_puts("PROGRAM release end status=unexpected-state\n");return;
    }
    for(unsigned n=0;n<6;n++){
        if(tuner_read_register(bank,0xd6+n,&single[n])){
            uart_puts("PROGRAM release end status=validation-read-failed\n");return;
        }
    }
    if(tuner_read_burst(bank,0xd6,ordinary,6,&actual) || actual!=6){
        uart_puts("PROGRAM release end status=validation-burst-failed\n");return;
    }
    for(unsigned n=0;n<6;n++)if(ordinary[n]!=single[n]){
        uart_puts("PROGRAM release end status=validation-mismatch\n");return;
    }
    uart_puts("PROGRAM release ordinary=verified\n");
    for(unsigned mode=0;mode<3 && !failed;mode++){
        if(mode){
            changed=1;
            /* Manufacturer release first sets bit1 while bit0 is still 1,
             * then clears bit0. Upper bits are known E0 by the guard. */
            if(mode==2 && tuner_write_register(bank,0xf3,0xe3)){failed=1;break;}
            if(tuner_write_register(bank,0xf3,modes[mode])){failed=1;break;}
        }
        if(tuner_read_register(bank,0xf3,&after)){
            uart_puts("PROGRAM release control-read-failed\n");failed=1;break;
        }
        observed[mode]=after;
        uart_puts("PROGRAM release control requested=");uart_hex(modes[mode]);
        uart_puts(" observed=");uart_hex(after);uart_puts("\n");
        /* The board reads E3 as E1 and E2 as E0: bit1 reads low in both
         * observed transitions. Accept only these measured alternatives;
         * its write-only/self-clearing semantics are still unclassified. */
        if(after!=modes[mode] && !(mode==1 && after==0xe1) &&
           !(mode==2 && after==original)){failed=1;break;}
        for(unsigned port=0;port<2 && !failed;port++){
            for(unsigned n=0;n<8;n++){
                if(tuner_read_register(bank,0xf6+port,&data[mode][0][port][n])){failed=1;break;}
                count[mode][0][port]++;
            }
            if(!failed && (tuner_read_burst(bank,0xf6+port,data[mode][1][port],8,&count[mode][1][port]) ||
                           count[mode][1][port]!=8))failed=1;
        }
        if(!failed && (tuner_read_register(bank,0xf4,&after) || after!=high ||
                       tuner_read_register(bank,0xf5,&after) || after!=low))failed=1;
    }
    unsigned restored=1;
    if(changed)restored=!tuner_write_register(bank,0xf3,original);
    /* Check every saved register even if a prior check fails. */
    if(tuner_read_register(bank,0xf3,&after) || after!=original)restored=0;
    if(tuner_read_register(bank,0xf4,&after) || after!=high)restored=0;
    if(tuner_read_register(bank,0xf5,&after) || after!=low)restored=0;
    for(unsigned mode=0;mode<3;mode++)for(unsigned kind=0;kind<2;kind++)for(unsigned port=0;port<2;port++){
        uart_puts("PROGRAM release mode=");uart_hex(modes[mode]);
        uart_puts(" observed=");uart_hex(observed[mode]);
        uart_puts(kind?" type=burst":" type=single");uart_puts(" port=");uart_hex(0xf6+port);
        uart_puts(" count=");uart_hex(count[mode][kind][port]);uart_puts(" bytes=");
        for(unsigned n=0;n<count[mode][kind][port] && n<8;n++){uart_hex(data[mode][kind][port][n]);uart_puts(" ");}
        uart_puts("\n");
    }
    if(!restored)uart_puts("PROGRAM release end status=restore-failed\n");
    else if(failed)uart_puts("PROGRAM release end status=read-failed-restored\n");
    else uart_puts("PROGRAM release end status=read-restored-unclassified\n");
}
