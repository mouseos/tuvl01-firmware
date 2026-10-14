/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"
#include "FreeRTOS.h"
#include "task.h"
void tuner_program_mailbox_select(void){
    TickType_t start=xTaskGetTickCount();int index;
    uart_puts("MAILBOX select start\n");
    for(;;){
        index=uart_getc();if(index>=0)break;
        if((TickType_t)(xTaskGetTickCount()-start)>=pdMS_TO_TICKS(2000)){
            uart_puts("MAILBOX probe end status=operand-transport-timeout\n");return;
        }
        vTaskDelay(1);
    }
    uint16_t operand=tuner_program_mailbox_known_operand(index);
    if(!operand){uart_puts("MAILBOX probe end status=unknown-operand\n");return;}
    (void)tuner_program_mailbox_operand(operand);
}
