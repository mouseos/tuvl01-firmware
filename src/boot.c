/* SPDX-License-Identifier: MIT; recovery is always the default boot mode. */
#include "board.h"
#include "image.h"
#include "usb.h"
#include "string.h"
static Image image;
static uint32_t written,pending_offset,status,action,update_pos,erase_end;
static unsigned out_command,ready,update_state,loaded;
static uint32_t flash_crc_state;
static void (*vectors[256])(void) __attribute__((aligned(1024)));
enum { ERR_OK,ERR_IMAGE,ERR_ORDER,ERR_CRC,ERR_FLASH,ERR_BUSY };
static void info(uint8_t *p) {
    /* All protocol multibyte values are big endian. */
    uint32_t v[8]={0x5455564c,1,status,written,ready,update_state,flash_id(),0x424f4f54};
    memcpy(p,v,sizeof v);
}
int usb_request(unsigned type,unsigned req,unsigned value,unsigned index,unsigned len,uint8_t *reply) {
    out_command=0;
    if(type==0xc0 && req==1 && !value && !index && len==32){info(reply);return 32;}
    if(type!=0x40 || update_state || action)return -1;
    if(req==2 && len==32 && !value && !index){out_command=2;return 0;}
    if(req==3 && len && len<=64 && !ready && loaded && written<=image.size && len<=image.size-written){
        pending_offset=((uint32_t)index<<16)|value;
        if(pending_offset!=written)return -1;
        out_command=3;return 0;
    }
    if(len || value || index)return -1;
    if(req==4 && loaded && written==image.size){
        ready=crc32((void *)APP_BASE,image.size)==image.crc;
        status=ready?ERR_OK:ERR_CRC;return 0;
    }
    if(req==5 && ready){action=1;return 0;} /* execute after status ACK */
    if(req==6 && ready){action=2;return 0;} /* persistent update */
    if(req==7){action=3;return 0;} /* read flash application */
    return -1;
}
int usb_out(const uint8_t *p,unsigned n) {
    if(out_command==2 && n==32){
        ready=loaded=written=0;
        memcpy(&image,p,32);
        if(!image_valid(&image)){status=ERR_IMAGE;return -1;}
        loaded=1;status=ERR_OK;out_command=0;return 0;
    }
    if(out_command==3 && pending_offset==written && n<=image.size-written){
        memcpy((void *)(APP_BASE+written),p,n);written+=n;out_command=0;return 0;
    }
    status=ERR_ORDER;out_command=0;return -1;
}
static void run(void) {
    uart_puts("RUN application CRC checked\n");usb_detach();
    for(volatile unsigned n=0;n<2000000;n++){}
    /* Cache is left in reset-disabled state; no application code is reused. */
    ((void (*)(void))APP_BASE)();
    fault();
}
static void load(void) {
    ready=loaded=written=0;
    if(flash_read(APP_FLASH,&image,32) || !image_valid(&image)){status=ERR_IMAGE;return;}
    loaded=1;update_state=5;status=ERR_BUSY;flash_crc_state=UINT32_MAX;
    uart_puts("LOAD size=");uart_hex(image.size);uart_puts(" expected_crc=");uart_hex(image.crc);uart_puts("\n");
}
void usb_idle(void) {
    unsigned a=action;action=0;
    if(a==1)run();
    if(a==3)load();
    if(a==2){
        if(flash_id()!=0x014017){status=ERR_FLASH;return;}
        update_pos=APP_FLASH;
        erase_end=APP_FLASH+((image.size+32+4095)&~4095UL);
        update_state=1;status=ERR_BUSY;
    }
}
static void update_poll(void) {
    if(!update_state)return;
    int sr=flash_status();
    if(sr<0){status=ERR_FLASH;update_state=0;return;}
    if(sr&1)return; /* USB continues to run while NOR is busy. */
    if(update_state==5){
        if(written<image.size){
            uint32_t n=image.size-written;if(n>64)n=64;
            uint8_t data[64];
            if(flash_read(APP_FLASH+32+written,data,n)){
                status=ERR_FLASH;update_state=0;loaded=0;return;
            }
            flash_crc_state=crc32_update(flash_crc_state,data,n);
            memcpy((void *)(APP_BASE+written),data,n);
            if(!written){
                uart_puts("LOAD first_flash=");for(unsigned i=0;i<n && i<16;i++)uart_hex(data[i]);
                uart_puts("\nLOAD first_ram=");for(unsigned i=0;i<n && i<16;i++)uart_hex(R8(APP_BASE+i));uart_puts("\n");
            }
            written+=n;return;
        }
        uint32_t ram_crc=crc32((void *)APP_BASE,image.size);
        uart_puts("LOAD flash_crc=");uart_hex(~flash_crc_state);uart_puts(" ram_crc=");uart_hex(ram_crc);uart_puts("\n");
        ready=ram_crc==image.crc && ~flash_crc_state==image.crc;
        status=ready?ERR_OK:ERR_CRC;update_state=0;
        uart_puts(ready?"FLASH application validated; explicit run required\n":"FLASH application CRC failed\n");
        return;
    }
    if(update_state==1){
        if(update_pos<erase_end){
            if(flash_erase(update_pos)){status=ERR_FLASH;update_state=0;return;}
            update_pos+=4096;return;
        }
        update_pos=0;update_state=2;
    }
    if(update_state==2){
        if(update_pos<image.size){
            uint32_t a=APP_FLASH+32+update_pos,n=256-(a&255);
            if(n>image.size-update_pos)n=image.size-update_pos;
            if(flash_program(a,(void *)(APP_BASE+update_pos),n)){status=ERR_FLASH;update_state=0;return;}
            update_pos+=n;return;
        }
        update_state=3;update_pos=0;
    }
    if(update_state==3){
        /* Compare payload before committing the header. */
        uint8_t buf[64];
        if(update_pos<image.size){
            uint32_t n=image.size-update_pos;if(n>64)n=64;
            if(flash_read(APP_FLASH+32+update_pos,buf,n) || memcmp(buf,(void *)(APP_BASE+update_pos),n)){
                status=ERR_FLASH;update_state=0;return;
            }
            update_pos+=n;return;
        }
        if(flash_program(APP_FLASH,&image,32)){status=ERR_FLASH;update_state=0;return;}
        update_state=4;return;
    }
    if(update_state==4){
        Image check;
        status=flash_read(APP_FLASH,&check,32) || memcmp(&check,&image,32)?ERR_FLASH:ERR_OK;
        update_state=0;
    }
}
static int uart_read_bytes(uint8_t *p,unsigned n) {
    while(n--){
        unsigned timeout=2000000;int c;
        do {c=uart_getc();} while(c<0 && --timeout);
        if(c<0){ready=loaded=0;status=ERR_ORDER;uart_puts("UART timeout\n");return -1;}
        *p++=(uint8_t)c;
    }
    return 0;
}
static void uart_command(int c) {
    uint8_t packet[64];
    if(c=='i'){
        uart_puts("UART recovery status=");uart_hex(status);uart_puts(" written=");uart_hex(written);
        uart_puts(" ready=");uart_hex(ready);uart_puts(" busy=");uart_hex(update_state);uart_puts("\n");
    }
    if(update_state || action)return;
    if(c=='b'){
        uart_puts("UART header\n");
        if(uart_read_bytes(packet,32))return;
        usb_request(0x40,2,0,0,32,packet);
        int accepted=usb_out(packet,32);
        uart_puts(accepted?"UART rejected\n":"UART accepted\n");
    }
    if(c=='w'){
        uart_puts("UART chunk\n");
        if(uart_read_bytes(packet,6))return;
        uint32_t offset=((uint32_t)packet[0]<<24)|((uint32_t)packet[1]<<16)|((uint32_t)packet[2]<<8)|packet[3];
        unsigned n=((unsigned)packet[4]<<8)|packet[5];
        if(!n || n>64 || usb_request(0x40,3,offset&0xffff,offset>>16,n,packet)){
            uart_puts("UART rejected\n");return;
        }
        uart_puts("UART data\n");
        if(uart_read_bytes(packet,n))return;
        int accepted=usb_out(packet,n);
        uart_puts(accepted?"UART rejected\n":"UART accepted\n");
    }
    if(c=='s'){
        int accepted=usb_request(0x40,4,0,0,0,packet);
        uart_puts(!accepted && ready?"UART sealed\n":"UART rejected\n");
    }
    if(c=='p'){
        int accepted=usb_request(0x40,6,0,0,0,packet);
        uart_puts(!accepted?"UART save queued\n":"UART rejected\n");
        usb_idle();
    }
    if(c=='l')load();
    if(c=='r' && ready)run();
}
void firmware_main(void) {
    board_init();
    /* Manual 32.2.14: the first 128 KiB also requires SYSCR5 RRAMWE.
       Configure from high-speed RAM, outside the retention RAM region. */
    uint8_t retention_write_before=R8(0xfffe0428);
    R8(0xfffe0428)=0x0f;
    uint8_t retention_write_after=R8(0xfffe0428);
    for(unsigned i=0;i<256;i++)vectors[i]=fault;
    uintptr_t v=(uintptr_t)vectors;__asm__ volatile("ldc %0,vbr" :: "r"(v):"memory");
    uart_puts("TUVL01 independent recovery boot\n");
    uart_puts("DIAG build 5 CCR=");uart_hex(R32(0xfffc1000));
    uart_puts(" SYSCR3=");uart_hex(R8(0xfffe0420));uart_puts(" SYSCR4=");uart_hex(R8(0xfffe0424));uart_puts("\n");
    uart_puts("RAM SYSCR5 before=");uart_hex(retention_write_before);
    uart_puts(" after=");uart_hex(retention_write_after);uart_puts("\n");
    flash_init();uart_puts("NOR JEDEC=");uart_hex(flash_id());uart_puts("\n");
    usb_init();
    for(;;){
        usb_poll();update_poll();
        int c=uart_getc();
        if(c=='u')usb_debug();
        uart_command(c);
    }
}
