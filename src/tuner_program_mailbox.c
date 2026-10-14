/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"

/* Experimental instruction operand, not an established IQ/sample reader.
 * The host must load this image and initialize the complete stock patch
 * before the probe, then reload it afterwards. Parity is not memory readback. */
static int mailbox_transfer(uint16_t operand,unsigned d5){
    uint8_t v,expected;
    if(d5)uart_puts(d5==2?"MAILBOX transfer source=register-D5-write20\n":"MAILBOX transfer source=register-D5\n");
    else {uart_puts("MAILBOX transfer operand=");uart_hex(operand);uart_puts("\n");}
    /* Halt before changing the address; trigger transfer again AFTER setting
     * the address, following the stock patch loader's latch/reset sequence. */
    if(tuner_write_register(0x61,0xf3,0xe3) || tuner_read_register(0x61,0xf3,&v))return -1;
    uart_puts("MAILBOX transfer halted f3=");uart_hex(v);uart_puts("\n");
    if(v!=0xe1 && v!=0xe3)return -1;
    if(tuner_write_register(0x61,0xf4,2) || tuner_write_register(0x61,0xf5,0x98) ||
       tuner_read_register(0x61,0xf4,&v))return -1;
    uart_puts("MAILBOX transfer address f4=");uart_hex(v);uart_puts("\n");
    if(v!=2)return -1;
    if(tuner_read_register(0x61,0xf5,&v))return -1;
    uart_puts("MAILBOX transfer address f5=");uart_hex(v);uart_puts("\n");
    if(v!=0x98)return -1;
    /* Stock loader arms F3 then writes F6 without an intervening read.
     * Write acknowledgement is not verification of the resulting F3 value. */
    if(tuner_write_register(0x61,0xf3,0xe3))return -1;
    if(d5?tuner_program_mailbox_write_d5_record(&expected,d5==2):tuner_program_mailbox_write_record(operand,&expected))return -1;
    uart_puts("MAILBOX transfer arm-payload writes acknowledged\n");
    /* Expected parity covers all 1304 bytes, including the operand change. */
    unsigned matches=0;
    /* Eight finite observations, spaced by UART output and I2C latency.
     * Require the final three to match; never ignore a parity mismatch.
     * The time interval is not a calibrated sampling rate. */
    for(unsigned n=0;n<8;n++){
        if(tuner_read_register(0x61,0xf8,&v))return -1;
        uart_puts("MAILBOX transfer parity index=");uart_hex(n);
        uart_puts(" f8=");uart_hex(v);
        uart_puts(" expected=");uart_hex(expected);uart_puts("\n");
        if(((v>>4)&1)==expected)matches++;else matches=0;
    }
    return matches>=3?0:-1;
}
static int mailbox_samples(unsigned phase,unsigned d5){
    for(unsigned n=0;n<16;n++){
        uint8_t sub,main,d4=0,data=0;
        if(tuner_read_register(0x60,0x6d,&sub) || tuner_read_register(0x61,0x6d,&main))return -1;
        if(d5 && (tuner_read_register(0x61,0xd4,&d4) || tuner_read_register(0x61,0xd5,&data)))return -1;
        uart_puts("MAILBOX sample phase=");uart_hex(phase);
        uart_puts(" index=");uart_hex(n);uart_puts(" sub6d=");uart_hex(sub);
        uart_puts(" main6d=");uart_hex(main);uart_puts("\n");
        if(d5){uart_puts("MAILBOX source phase=");uart_hex(phase);uart_puts(" index=");uart_hex(n);
            uart_puts(" d4=");uart_hex(d4);uart_puts(" d5=");uart_hex(data);uart_puts("\n");}
    }
    return 0;
}
static int mailbox_probe(uint16_t operand,unsigned d5){
    uint8_t control,high,low,v;
    unsigned failed=0,restored=1;
    unsigned known=0;
    for(unsigned n=0;tuner_program_mailbox_known_operand(n);n++)
        if(operand==tuner_program_mailbox_known_operand(n))known=1;
    if(!d5 && !known){uart_puts("MAILBOX probe end status=unknown-operand\n");return 0;}
    if(d5)uart_puts(d5==2?"MAILBOX probe start source=register-D5-write20 address=00000298 count=00000518\n":"MAILBOX probe start source=register-D5 address=00000298 count=00000518\n");
    else {uart_puts("MAILBOX probe start address=00000298 count=00000518 operand=");uart_hex(operand);uart_puts("\n");}
    if(!tuner_program_mailbox_original_valid()){
        uart_puts("MAILBOX probe end status=unexpected-source-payload\n");return 0;
    }
    if(tuner_read_register(0x61,0xf3,&control) || tuner_read_register(0x61,0xf4,&high) ||
       tuner_read_register(0x61,0xf5,&low)){
        uart_puts("MAILBOX probe end status=i2c-failed-before-change\n");return 0;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("MAILBOX probe end status=unexpected-state\n");return 0;
    }
    if(mailbox_samples(0,d5)){
        uart_puts("MAILBOX probe end status=baseline-read-failed\n");return 0;
    }
    /* Any attempted transfer can have reached the chip: always restore. */
    if(mailbox_transfer(operand,d5))failed=1;
    if(!failed && (tuner_write_register(0x61,0xf3,control) ||
                  tuner_read_register(0x61,0xf3,&v) || v!=control))failed=1;
    if(!failed && mailbox_samples(1,d5))failed=1;
    /* Retry a failed restoration once from a fully reselected address.
     * Never continue streaming bytes after an uncertain failed payload byte. */
    if(mailbox_transfer(0x0f0d,0) && mailbox_transfer(0x0f0d,0))restored=0;
    if(restored){
        if(tuner_write_register(0x61,0xf4,high))restored=0;
        if(tuner_write_register(0x61,0xf5,low))restored=0;
        if(tuner_write_register(0x61,0xf3,control))restored=0;
    }
    if(tuner_read_register(0x61,0xf3,&v) || v!=control)restored=0;
    if(tuner_read_register(0x61,0xf4,&v) || v!=high)restored=0;
    if(tuner_read_register(0x61,0xf5,&v) || v!=low)restored=0;
    if(restored && mailbox_samples(2,d5))failed=1;
    uart_puts(!restored?"MAILBOX probe end status=restore-failed-reinitialize-required\n":
              failed?"MAILBOX probe end status=read-failed-restored-reinitialize-required\n":
                     "MAILBOX probe end status=read-restored-unclassified-reinitialize-required\n");
    return !failed && restored;
}
int tuner_program_mailbox_operand(uint16_t operand){return mailbox_probe(operand,0);}
void tuner_program_mailbox_d5(void){(void)mailbox_probe(0,1);}
void tuner_program_mailbox_d5_write20(void){(void)mailbox_probe(0,2);}
void tuner_program_mailbox_probe(void){(void)tuner_program_mailbox_operand(0x0f0c);}
void tuner_program_mailbox_sweep(void){
    unsigned completed=0,failed=0;
    uart_puts("MAILBOX sweep start\n");
    for(unsigned n=0;tuner_program_mailbox_known_operand(n);n++){
        uint16_t operand=tuner_program_mailbox_known_operand(n);
        uart_puts("MAILBOX sweep item index=");uart_hex(n);
        uart_puts(" operand=");uart_hex(operand);uart_puts("\n");
        if(!tuner_program_mailbox_operand(operand)){failed=1;break;}
        completed++;
    }
    uart_puts("MAILBOX sweep completed=");uart_hex(completed);uart_puts("\n");
    uart_puts(failed?"MAILBOX sweep end status=failed-reinitialize-required\n":
                    "MAILBOX sweep end status=read-restored-unclassified-reinitialize-required\n");
}
