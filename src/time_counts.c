/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "time_counts.h"
uint32_t board_time_counts(void){
    /* Stabilize the epoch; if CMF rises, re-read the new counter phase.
     * Never clear CMF or change the RTOS timer configuration. */
    taskENTER_CRITICAL();
    uint32_t tick=xTaskGetTickCount();
    uint32_t period=(uint32_t)R16(0xfffec006)+1U;
    unsigned before=R16(0xfffec002)&0x80U;
    unsigned count=R16(0xfffec004);
    unsigned after=R16(0xfffec002)&0x80U;
    if(before!=after)count=R16(0xfffec004);
    if(after)tick++;
    uint32_t result=tick*period+count;
    taskEXIT_CRITICAL();
    return result;
}
