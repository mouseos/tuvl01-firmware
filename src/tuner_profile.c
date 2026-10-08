/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "sdio.h"
#include "tuner.h"
#include "tuner_profile.h"
static int read(unsigned bank,unsigned reg,uint8_t *v){
    if(tuner_read_register(bank,reg,v))return -1;
    uart_puts("TUNE read bank=");uart_hex(bank);uart_puts(" reg=");uart_hex(reg);
    uart_puts(" value=");uart_hex(*v);uart_puts("\n");return 0;
}
static int write(unsigned bank,unsigned reg,unsigned v){
    if(tuner_write_register(bank,reg,(uint8_t)v))return -1;
    uart_puts("TUNE ACK bank=");uart_hex(bank);uart_puts(" reg=");uart_hex(reg);
    uart_puts(" value=");uart_hex(v);uart_puts("\n");return 0;
}
void tuner_profile_receive(void){
    uint8_t p[32],v;unsigned pos=0;
    TickType_t start=xTaskGetTickCount();
    uart_puts("TUNE profile ready bytes=32\n");
    while(pos<sizeof p){
        int c=uart_getc();
        if(c>=0)p[pos++]=(uint8_t)c;
        else {sdio_wifi_poll();vTaskDelay(1);}
        if((TickType_t)(xTaskGetTickCount()-start)>=pdMS_TO_TICKS(3000)){
            uart_puts("TUNE end status=transport-timeout\n");return;
        }
    }
    if(!tuner_profile_valid(p)){uart_puts("TUNE end status=rejected\n");return;}
    uart_puts(p[27]==2?"TUNE mode=UHF-native-candidate\n":
              p[27]?"TUNE mode=UHF-partial-experimental\n":"TUNE mode=VLF-control\n");
    if(read(0x60,0xb9,&v))goto failed;
    uart_puts("TUNE pre-setting B9=");uart_hex(v);uart_puts("\n");
    if(read(0x60,0xd6,&v))goto failed;
    if(!(v&1)){uart_puts("TUNE end status=not-calibrated\n");return;}
    /* Establish the UHF base for partial as well as full tuning: calibration
     * leaves bank2:04 at 4, so partial must not depend on a prior full tune.
     * This register's readback semantics remain unknown; an I2C ACK does not
     * establish broadcast lock or valid TS. RF constants remain host inputs. */
    if(write(0x62,4,8))goto failed;
    for(unsigned n=0;n<3;n++)if(write(0x61,0x0d+n,p[8+n]))goto failed;
    for(unsigned n=0;n<3;n++)if(write(0x61,0x0a+n,p[11+n]))goto failed;
    if(read(0x61,0,&v) || write(0x61,0,v&~2U) || write(0x62,0xf2,p[14]))goto failed;
    if(p[27]==2){
        if(read(0x60,0x75,&v) || write(0x60,0x75,(v&0xf0)|p[16]))goto failed;
    }else if(write(0x60,0x75,p[16]))goto failed;
    for(unsigned n=1;n<3;n++)if(write(0x60,0x75+n,p[16+n]))goto failed;
    if(write(0x60,0x74,p[15]) || write(0x61,0xed,p[26]))goto failed;
    for(unsigned n=0;n<4;n++)if(write(0x60,0xc8+n,p[19+n]))goto failed;
    if(write(0x60,0x78,p[25]))goto failed;
    vTaskDelay(pdMS_TO_TICKS(10));
    unsigned frequency=((uint32_t)p[4]<<24|(uint32_t)p[5]<<16|(uint32_t)p[6]<<8|p[7])/1000;
    if(write(0x60,0xcc,frequency>>2) ||
       write(0x60,0xcd,((frequency&3)<<6)|(p[23]&0x3f)) ||
       write(0x60,0xce,0xc0|(p[24]&0x3f)))goto failed;
    vTaskDelay(pdMS_TO_TICKS(20));
    if(read(0x60,0xb9,&v))goto failed;
    uart_puts("TUNE pre-trigger B9=");uart_hex(v);uart_puts("\n");
    if(write(0x60,0xba,0))goto failed;
    for(unsigned attempt=0;attempt<11;attempt++){
        if(read(0x60,0xb9,&v))goto failed;
        if(v&0x80){
            /* Tuning completion is not broadcast lock or valid transport data. */
            if(read(0x60,0xcf,&v) || read(0x60,0xd0,&v) || read(0x61,0xf1,&v))goto failed;
            uart_puts("TUNE end status=sequence-complete\n");return;
        }
        if(attempt<10)vTaskDelay(pdMS_TO_TICKS(300));
    }
    uart_puts("TUNE end status=completion-timeout\n");return;
failed:
    uart_puts("TUNE end status=i2c-failed\n");
}
