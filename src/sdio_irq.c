/* SPDX-License-Identifier: MIT. Independent SH726A SDHI task wakeups. */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "sdio_irq.h"
#define S(o) R16(0xffffc800UL+(o))
static TaskHandle_t owner;
static unsigned enabled;
static volatile unsigned hits,spurious;
static unsigned waits,ready,timeouts;
static void mask(void){S(0x20)=0x03bd;S(0x22)=0x837f;}
int sdio_irq_set(unsigned selected){
    taskENTER_CRITICAL();mask();
    R16(0xfffe0c1e)&=(uint16_t)~0x0f00;
    enabled=0;owner=0;
    if(selected){
        owner=xTaskGetCurrentTaskHandle();
        if(!owner){taskEXIT_CRITICAL();return -1;}
        (void)ulTaskNotifyTake(pdTRUE,0);
        hits=spurious=waits=ready=timeouts=0;
        enabled=1;
        /* Equal to CMT priority: the integer context port cannot nest. */
        R16(0xfffe0c1e)|=0x0100;
    }
    taskEXIT_CRITICAL();return 0;
}
unsigned sdio_irq_enabled(void){return enabled;}
int sdio_irq_wait(unsigned info1,unsigned info2,uint32_t ticks){
    if(!enabled || !owner || !ticks)return -1;
    info1&=5;info2=(info2&0x0300)|0x807f;
    /* No other code uses this task's notification. Mask + drain + inspect
     * + arm is atomic against the level-1 ISR. Pending hardware status is
     * not cleared, so completion-before-wait is retained. */
    taskENTER_CRITICAL();mask();
    (void)ulTaskNotifyTake(pdTRUE,0);
    if((S(0x1c)&info1) || (S(0x1e)&info2)){
        ready++;taskEXIT_CRITICAL();return 0;
    }
    S(0x20)=(uint16_t)(0x03bd&~info1);
    S(0x22)=(uint16_t)(0x837f&~info2);
    waits++;taskEXIT_CRITICAL();
    unsigned notified=ulTaskNotifyTake(pdTRUE,ticks);
    taskENTER_CRITICAL();mask();taskEXIT_CRITICAL();
    if(!notified){timeouts++;return -1;}
    return 0;
}
void sdio_irq_handler(void){
    unsigned info1=S(0x1c)&~S(0x20)&5;
    unsigned info2=S(0x1e)&~S(0x22)&0x837f;
    mask(); /* Deassert IRQ without consuming CMD_END/DATAEND/FIFO status. */
    if(!enabled || !owner || !(info1|info2)){spurious++;return;}
    hits++;
    BaseType_t switch_required=pdFALSE;
    vTaskNotifyGiveFromISR(owner,&switch_required);
    if(switch_required)vTaskSwitchContext();
}
unsigned sdio_irq_counter(unsigned index){
    switch(index){
    case 0:return enabled;case 1:return hits;case 2:return waits;
    case 3:return ready;case 4:return timeouts;case 5:return spurious;
    default:return 0;
    }
}
