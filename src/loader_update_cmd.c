/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "image.h"
#include "loader_update.h"
static const char *name(int result){
    switch(result){
    case LOADER_OK:return "verified";
    case LOADER_BAD_CRC:return "rejected-crc";
    case LOADER_BAD_IMAGE:return "rejected-image";
    case LOADER_FLASH_ID:return "flash-id";
    case LOADER_PROTECTED:return "block-protected";
    case LOADER_ERASE:return "erase-failed";
    case LOADER_PROGRAM:return "program-failed";
    default:return "verify-failed";
    }
}
void loader_update_command(void){
    static uint8_t image[LOADER_SIZE];
    uint8_t crc[4];
    const unsigned total=LOADER_SIZE+4;
    uart_puts("LOADER update ready bytes=");uart_hex(total);uart_puts(" chunk=00000040\n");
    for(unsigned pos=0;pos<total;){
        unsigned n=total-pos;if(n>64)n=64;
        TickType_t start=xTaskGetTickCount();
        for(unsigned i=0;i<n;){
            int c=uart_getc();
            if(c>=0){
                if(pos+i<LOADER_SIZE)image[pos+i]=(uint8_t)c;else crc[pos+i-LOADER_SIZE]=(uint8_t)c;
                i++;
            }else if((TickType_t)(xTaskGetTickCount()-start)>=pdMS_TO_TICKS(3000)){
                uart_puts("LOADER update end status=transport-timeout\n");return;
            }
        }
        pos+=n;uart_puts("LOADER ack\n");
    }
    uint32_t wanted=((uint32_t)crc[0]<<24)|((uint32_t)crc[1]<<16)|((uint32_t)crc[2]<<8)|crc[3];
    int result=loader_image_check(image,wanted);
    if(!result)result=loader_update_apply(image);
    uart_puts("LOADER update end status=");uart_puts(name(result));uart_puts("\n");
}
