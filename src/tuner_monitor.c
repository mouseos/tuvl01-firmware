/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"
#include "tuner_monitor.h"
#include "FreeRTOS.h"
#include "task.h"
static void field(const char *label,unsigned n){uart_puts(label);uart_hex(n);}
void tuner_monitor(void){
    uint8_t a[4],b[4],v;
    uart_puts("TUNER monitor start\n");
    if(tuner_read_register(0x60,0xb9,&v))goto failed;
    field("TUNER completion B9=",v);uart_puts("\n");
    for(unsigned n=0;n<4;n++){
        if(tuner_read_register(0x61,0x94+n,a+n) ||
           tuner_read_register(0x62,0x86+n,b+n))goto failed;
    }
    field("TUNER full raw94=",a[0]);field(" raw95=",a[1]);
    field(" raw96=",a[2]);field(" raw97=",a[3]);uart_puts("\n");
    field("TUNER standalone raw86=",b[0]);field(" raw87=",b[1]);
    field(" raw88=",b[2]);field(" raw89=",b[3]);uart_puts("\n");
    field("TUNER full stage=",a[1]&15);field(" error_flags=",a[1]>>4);
    field(" WAFCLCK=",(a[3]>>5)&1);field(" FRMLCK=",(a[3]>>4)&1);
    field(" TMCCERR=",(a[3]>>3)&1);field(" PART=",(a[3]>>2)&1);uart_puts("\n");
    int state=tuner_frame_state(a[1],a[3]);
    uart_puts(state<0?"TUNER monitor end status=demod-error\n":
              state?"TUNER monitor end status=frame-lock\n":
                    "TUNER monitor end status=unlocked\n");
    /* Frame lock is not valid TS, channel identity, or sustained reception. */
    return;
failed:uart_puts("TUNER monitor end status=i2c-failed\n");
}
void tuner_fec_snapshot(void){
    /* Read-only raw windows used by the reference BER/PER and CN monitor.
     * No selector/reset writes: counters are not a measured error rate. */
    static const uint8_t windows[][3]={
        {0x61,0x8b,9},{0x61,0xc0,9},{0x62,0x80,6},{0x62,0xac,8},
        {0x61,0x35,1},{0x61,0xd9,1},{0x61,0xdc,1},{0x61,0xe2,1},
        {0x62,0x02,1},{0x62,0xa8,1},{0x62,0xc7,1},{0x62,0xcd,1},{0x62,0xe8,1},
        {0x62,0xed,3},{0x62,0xf8,1},{0x60,0xb1,1},
        {0x61,0xa1,1},{0x60,0xd6,3}
    };
    uart_puts("FEC snapshot start\n");
    for(unsigned w=0;w<sizeof windows/sizeof windows[0];w++){
        uint8_t bytes[9];
        for(unsigned n=0;n<windows[w][2];n++)
            if(tuner_read_register(windows[w][0],windows[w][1]+n,bytes+n))goto failed;
        field("FEC bank=",windows[w][0]);field(" start=",windows[w][1]);
        for(unsigned n=0;n<windows[w][2];n++)field(" byte=",bytes[n]);
        uart_puts("\n");
    }
    uart_puts("FEC snapshot end status=raw\n");return;
failed:uart_puts("FEC snapshot end status=i2c-failed\n");
}
void tuner_quality(void){
    /* Full-demodulator Layer-A/B measurement; restore every saved control.
     * Raw counts only: no unverified rate, dB or signal-quality conversion. */
    static const uint8_t control[]={0x8b,0x8e,0x90,0x91,0x92,0x93};
    uint8_t saved[sizeof control],v,gate[3],cn[2],raw[5],again[5];
    const char *result="i2c-failed";unsigned changed=0;
    uart_puts("QUALITY start\n");
    if(tuner_read_register(0x61,0x97,&v))goto finish;
    if((v&0x18)!=0x10){result="not-locked";goto finish;}
    if(tuner_read_register(0x61,0x86,gate) || tuner_read_register(0x61,0x87,gate+1) ||
       tuner_read_register(0x61,0x89,gate+2))goto finish;
    field("QUALITY CN gate86=",gate[0]);field(" gate87=",gate[1]);field(" gate89=",gate[2]);uart_puts("\n");
    TickType_t start=xTaskGetTickCount();
    do{
        if(tuner_read_register(0x61,0xbf,&v))goto finish;
        if((v&3)==3)break;
        vTaskDelay(pdMS_TO_TICKS(10));
    }while((TickType_t)(xTaskGetTickCount()-start)<pdMS_TO_TICKS(500));
    if(tuner_read_register(0x61,0xc0,cn) || tuner_read_register(0x61,0xc1,cn+1))goto finish;
    field("QUALITY CN BF=",v);field(" raw=",((unsigned)cn[0]<<8)|cn[1]);
    uart_puts((gate[0]&1)||(gate[1]&1)||(gate[2]&0x80)?" status=gate-invalid\n":
              (v&3)==3?" status=ready-raw\n":" status=not-ready\n");
    for(unsigned n=0;n<sizeof control;n++)
        if(tuner_read_register(0x61,control[n],saved+n))goto finish;
    uint8_t setting[]={ (saved[0]&0xc0)|0x10,4,(saved[2]&0xf0)|5,
                       (saved[3]&0xc0)|0x30,4,saved[5]&0x7f };
    changed=1;
    for(unsigned n=0;n<sizeof control;n++)
        if(tuner_write_register(0x61,control[n],setting[n]))goto finish;
    unsigned zero_denominator=0;
    for(unsigned per=0;per<2;per++)for(unsigned layer=0;layer<2;layer++){
        unsigned selector=layer+1,reg=per?0x93:0x90;
        uint8_t selected=per?((saved[5]&0x7c)|0x80|selector):((setting[2]&0xfc)|selector);
        /* Native full-demodulator reader requires both C3 bits:
         * BER 7/6, PER A 5/4, PER B 3/2. One bit alone can be stale. */
        uint8_t ready_mask=per?(0x30>>(2*layer)):0xc0;
        if(tuner_write_register(0x61,reg,selected))goto finish;
        start=xTaskGetTickCount();
        do{
            if(tuner_read_register(0x61,0xc3,&v))goto finish;
            if((v&ready_mask)==ready_mask)break;
            vTaskDelay(pdMS_TO_TICKS(10));
        }while((TickType_t)(xTaskGetTickCount()-start)<pdMS_TO_TICKS(1000));
        uart_puts(layer?"QUALITY Layer-B":"QUALITY Layer-A");
        uart_puts(per?" PER":" BER");field(" C3=",v);field(" ready_mask=",ready_mask);uart_puts("\n");
        if((v&ready_mask)!=ready_mask){result="counter-not-ready";goto finish;}
        for(unsigned attempt=0;attempt<3;attempt++){
            unsigned mismatch=0;
            for(unsigned n=0;n<5;n++)if(tuner_read_register(0x61,0xc4+n,raw+n))goto finish;
            for(unsigned n=0;n<5;n++){
                if(tuner_read_register(0x61,0xc4+n,again+n))goto finish;
                if(raw[n]!=again[n])mismatch=1;
            }
            if(!mismatch)break;
            if(attempt==2){result="counter-unstable";goto finish;}
        }
        uart_puts(layer?"QUALITY Layer-B":"QUALITY Layer-A");uart_puts(per?" PER":" BER");
        field(" count=",((unsigned)raw[0]<<16)|((unsigned)raw[1]<<8)|raw[2]);
        field(" denominator=",((unsigned)raw[3]<<8)|raw[4]);
        uart_puts((raw[3]|raw[4])?" status=counts-raw\n":" status=zero-denominator\n");
        if(!(raw[3]|raw[4]))zero_denominator=1;
    }
    result=zero_denominator?"zero-denominator":"counts-raw";
finish:
    if(changed){
        unsigned bad=0;
        for(unsigned n=sizeof control;n>0;n--)
            if(tuner_write_register(0x61,control[n-1],saved[n-1]))bad=1;
        for(unsigned n=0;n<sizeof control;n++)
            if(tuner_read_register(0x61,control[n],&v) || v!=saved[n])bad=1;
        uart_puts(bad?"QUALITY controls status=restore-failed\n":"QUALITY controls status=restored\n");
        if(bad)result="restore-failed";
    }
    uart_puts("QUALITY end status=");uart_puts(result);uart_puts("\n");
}
