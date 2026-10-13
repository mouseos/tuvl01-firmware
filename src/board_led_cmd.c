/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "board_led.h"
void board_led_command(void){
    TickType_t begin=xTaskGetTickCount();
    int c;
    uart_puts("LED command start\n");
    while((c=uart_getc())<0){
        if((TickType_t)(xTaskGetTickCount()-begin)>=pdMS_TO_TICKS(2000)){
            uart_puts("LED command end status=transport-timeout\n");return;
        }
        vTaskDelay(1);
    }
    int type=board_led_init();
    if(type<0){uart_puts("LED command end status=no-led-wiring\n");return;}
    uart_puts("LED strap=");uart_hex((unsigned)type);uart_puts("\n");
    if(c==0xff){board_led_auto();uart_puts("LED command end status=automatic\n");return;}
    board_led_set(0,c&1);board_led_set(1,(c>>1)&1);
    uart_puts("LED command end status=driven\n");
}
