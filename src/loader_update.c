/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "image.h"
#include "loader_update.h"
static int contains_banner(const uint8_t *p){
    static const char banner[]=LOADER_BANNER;
    for(uint32_t i=0;i+sizeof banner-1<=LOADER_SIZE;i++){
        uint32_t k=0;
        while(k<sizeof banner-1 && p[i+k]==(uint8_t)banner[k])k++;
        if(k==sizeof banner-1)return 1;
    }
    return 0;
}
int loader_image_check(const uint8_t *image,uint32_t crc){
    if(!image)return LOADER_BAD_IMAGE;
    if(crc32(image,LOADER_SIZE)!=crc)return LOADER_BAD_CRC;
    return contains_banner(image)?LOADER_OK:LOADER_BAD_IMAGE;
}
static int wait_idle(void){
    for(unsigned n=0;n<4000000;n++){
        int status=flash_status();
        if(status<0)return -1;
        if(!(status&1))return 0;
    }
    return -1;
}
static int write_sector(const uint8_t *image,uint32_t base){
    if(flash_boot_erase(base) || wait_idle())return LOADER_ERASE;
    for(uint32_t off=0;off<4096;off+=256){
        const uint8_t *page=image+base+off;
        unsigned blank=1;
        for(unsigned i=0;i<256;i++)if(page[i]!=0xff){blank=0;break;}
        if(blank)continue; /* erased state already matches */
        if(flash_boot_program(base+off,page,256) || wait_idle())return LOADER_PROGRAM;
    }
    for(uint32_t off=0;off<4096;off+=64){
        uint8_t chunk[64];
        if(flash_read(base+off,chunk,sizeof chunk))return LOADER_VERIFY;
        for(unsigned i=0;i<sizeof chunk;i++)if(chunk[i]!=image[base+off+i])return LOADER_VERIFY;
    }
    return LOADER_OK;
}
int loader_update_apply(const uint8_t *image){
    if(flash_id()!=0x014017)return LOADER_FLASH_ID;
    int status=flash_status();
    /* S25FL164K SR1: BP0..BP2 = bits 2..4, TB = bit 5, SEC = bit 6. */
    if(status<0 || (status&0x7c))return LOADER_PROTECTED;
    int result=write_sector(image,0x1000);
    if(result)return result;
    return write_sector(image,0);
}
