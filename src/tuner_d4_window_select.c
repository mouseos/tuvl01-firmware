/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"
#include "FreeRTOS.h"
#include "task.h"
static void select_index(unsigned experimental){
    TickType_t start=xTaskGetTickCount();int index;
    uart_puts("D4LIVE select start\n");
    for(;;){
        index=uart_getc();if(index>=0)break;
        if((TickType_t)(xTaskGetTickCount()-start)>=pdMS_TO_TICKS(2000)){
            uart_puts("D4LIVE probe end status=selector-transport-timeout\n");return;
        }
        vTaskDelay(1);
    }
    if(experimental)tuner_d4_window_live_experimental(index);
    else tuner_d4_window_live_selected(index);
}
void tuner_d4_window_live_select(void){select_index(0);}
void tuner_d4_window_experimental_select(void){select_index(1);}
