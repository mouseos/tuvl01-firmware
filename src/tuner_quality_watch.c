/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "tuner.h"
#include "tuner_ts.h"
#include "tuner_quality_watch.h"
/* Read-only snapshots: no BER selectors/resets or UART output during sampling.
 * One bounded RIIC register read per service pass. Values remain raw; repeated
 * reads detect change but are not an atomic hardware latch. */
static const uint8_t regs[]={0x95,0x97,0x86,0x87,0x89,0xbf,0xc0,0xc1,
                            0x8b,0x8e,0x90,0x91,0x92,0x93,0xc3,0xc4,0xc5,0xc6,0xc7,0xc8};
static const uint8_t repeated[]={1,5,6,7,14,15,16,17,18,19};
struct sample {TickType_t start,end,io_ticks;unsigned before,after,active,changed,failed;uint8_t raw[20],again[10];};
static struct sample samples[16];
static unsigned armed,count,step,in_sample;
static TickType_t armed_at,last_sample;
static void field(const char *s,unsigned n){uart_puts(s);uart_hex(n);}
void tuner_quality_watch_start(void){
    if(armed){uart_puts("QUALITY watch begin status=refused-active\n");return;}
    armed=1;count=step=in_sample=0;armed_at=xTaskGetTickCount();last_sample=armed_at;
    uart_puts("QUALITY watch begin status=armed\n");
}
void tuner_quality_watch_poll(void){
    if(!armed)return;
    TickType_t now=xTaskGetTickCount();
    if((TickType_t)(now-armed_at)>=pdMS_TO_TICKS(30000)){armed=0;return;}
    if(!in_sample){
        if(count && (TickType_t)(now-last_sample)<pdMS_TO_TICKS(1000))return;
        struct sample fresh={0};samples[count]=fresh;
        samples[count].start=last_sample=now;
        samples[count].before=tuner_ts_stream_packet_count();
        samples[count].active=tuner_ts_stream_active()!=0;
        step=0;in_sample=1;
    }
    struct sample *s=samples+count;
    unsigned index=step<20?step:repeated[step-20];
    uint8_t *dest=step<20?s->raw+index:s->again+(step-20);
    TickType_t before=xTaskGetTickCount();
    int result=tuner_read_register(0x61,regs[index],dest);
    s->io_ticks+=(TickType_t)(xTaskGetTickCount()-before);
    if(result){s->failed=step+1;step=30;}
    else{
        if(step>=20 && *dest!=s->raw[index])s->changed|=1U<<index;
        step++;
    }
    if(step==30){
        s->end=xTaskGetTickCount();s->after=tuner_ts_stream_packet_count();
        s->active|=(tuner_ts_stream_active()!=0)<<1;
        count++;in_sample=0;
        if(count==16)armed=0;
    }
}
void tuner_quality_watch_dump(void){
    armed=0;
    field("QUALITY watch count=",count);field(" partial_reads=",in_sample?step:0);uart_puts("\n");
    for(unsigned n=0;n<count;n++){
        struct sample *s=samples+n;
        field("QUALITY watch sample=",n);field(" start=",s->start);field(" end=",s->end);
        field(" io_ticks=",s->io_ticks);field(" tx_before=",s->before);field(" tx_after=",s->after);
        field(" active=",s->active);field(" changed=",s->changed);field(" failed_read=",s->failed);
        for(unsigned i=0;i<20;i++)field(" raw=",s->raw[i]);
        for(unsigned i=0;i<10;i++)field(" again=",s->again[i]);
        uart_puts("\n");
    }
    uart_puts("QUALITY watch end status=raw\n");
}
