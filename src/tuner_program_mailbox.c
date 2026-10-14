/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"

/* Experimental instruction operand, not an established IQ/sample reader.
 * The host must load this image and initialize the complete stock patch
 * before the probe, then reload it afterwards. Parity is not memory readback. */
static int mailbox_transfer(uint8_t operand){
    uint8_t v;
    uart_puts("MAILBOX transfer operand=");uart_hex(operand);uart_puts("\n");
    /* Halt before changing the address; trigger transfer again AFTER setting
     * the address, following the stock patch loader's latch/reset sequence. */
    if(tuner_write_register(0x61,0xf3,0xe3) || tuner_read_register(0x61,0xf3,&v))return -1;
    uart_puts("MAILBOX transfer halted f3=");uart_hex(v);uart_puts("\n");
    if(v!=0xe1 && v!=0xe3)return -1;
    if(tuner_write_register(0x61,0xf4,4) || tuner_write_register(0x61,0xf5,0xe7) ||
       tuner_read_register(0x61,0xf4,&v))return -1;
    uart_puts("MAILBOX transfer address f4=");uart_hex(v);uart_puts("\n");
    if(v!=4)return -1;
    if(tuner_read_register(0x61,0xf5,&v))return -1;
    uart_puts("MAILBOX transfer address f5=");uart_hex(v);uart_puts("\n");
    if(v!=0xe7)return -1;
    if(tuner_write_register(0x61,0xf3,0xe3) || tuner_read_register(0x61,0xf3,&v))return -1;
    uart_puts("MAILBOX transfer armed f3=");uart_hex(v);uart_puts("\n");
    if(v!=0xe1 && v!=0xe3)return -1;
    const uint8_t payload[3]={0xc5,0x0f,operand};
    if(tuner_write_burst(0x61,0xf6,payload,3))return -1;
    /* C5/0F/0C has even bit parity; C5/0F/0D has odd parity. */
    unsigned matches=0;
    /* Eight finite observations, spaced by UART output and I2C latency.
     * Require the final three to match; never ignore a parity mismatch.
     * The time interval is not a calibrated sampling rate. */
    for(unsigned n=0;n<8;n++){
        if(tuner_read_register(0x61,0xf8,&v))return -1;
        uart_puts("MAILBOX transfer parity index=");uart_hex(n);
        uart_puts(" f8=");uart_hex(v);
        uart_puts(" expected=");uart_hex(operand==0x0d);uart_puts("\n");
        if(((v>>4)&1)==(operand==0x0d))matches++;else matches=0;
    }
    return matches>=3?0:-1;
}
static int mailbox_samples(unsigned phase){
    for(unsigned n=0;n<16;n++){
        uint8_t sub,main;
        if(tuner_read_register(0x60,0x6d,&sub) || tuner_read_register(0x61,0x6d,&main))return -1;
        uart_puts("MAILBOX sample phase=");uart_hex(phase);
        uart_puts(" index=");uart_hex(n);uart_puts(" sub6d=");uart_hex(sub);
        uart_puts(" main6d=");uart_hex(main);uart_puts("\n");
    }
    return 0;
}
void tuner_program_mailbox_probe(void){
    uint8_t control,high,low,v;
    unsigned failed=0,restored=1;
    uart_puts("MAILBOX probe start address=000004e7 operand=00000f0c\n");
    if(!tuner_program_mailbox_original_valid()){
        uart_puts("MAILBOX probe end status=unexpected-source-payload\n");return;
    }
    if(tuner_read_register(0x61,0xf3,&control) || tuner_read_register(0x61,0xf4,&high) ||
       tuner_read_register(0x61,0xf5,&low)){
        uart_puts("MAILBOX probe end status=i2c-failed-before-change\n");return;
    }
    if(control!=0xe0 || high!=2 || low!=0x98){
        uart_puts("MAILBOX probe end status=unexpected-state\n");return;
    }
    if(mailbox_samples(0)){
        uart_puts("MAILBOX probe end status=baseline-read-failed\n");return;
    }
    /* Any attempted transfer can have reached the chip: always restore. */
    if(mailbox_transfer(0x0c))failed=1;
    if(!failed && (tuner_write_register(0x61,0xf3,control) ||
                  tuner_read_register(0x61,0xf3,&v) || v!=control))failed=1;
    if(!failed && mailbox_samples(1))failed=1;
    /* Retry a failed restoration once from a fully reselected address.
     * Never continue streaming bytes after an uncertain failed payload byte. */
    if(mailbox_transfer(0x0d) && mailbox_transfer(0x0d))restored=0;
    if(restored){
        if(tuner_write_register(0x61,0xf4,high))restored=0;
        if(tuner_write_register(0x61,0xf5,low))restored=0;
        if(tuner_write_register(0x61,0xf3,control))restored=0;
    }
    if(tuner_read_register(0x61,0xf3,&v) || v!=control)restored=0;
    if(tuner_read_register(0x61,0xf4,&v) || v!=high)restored=0;
    if(tuner_read_register(0x61,0xf5,&v) || v!=low)restored=0;
    if(restored && mailbox_samples(2))failed=1;
    uart_puts(!restored?"MAILBOX probe end status=restore-failed-reinitialize-required\n":
              failed?"MAILBOX probe end status=read-failed-restored-reinitialize-required\n":
                     "MAILBOX probe end status=read-restored-unclassified-reinitialize-required\n");
}
