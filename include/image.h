/* SPDX-License-Identifier: MIT */
#ifndef IMAGE_H
#define IMAGE_H
#include "board.h"
#define APP_CAPACITY (APP_LIMIT-APP_BASE-16384UL)
typedef struct { uint32_t magic,version,address,size,crc,entry,reserved,header_crc; } Image;
uint32_t crc32(const void *data,uint32_t n);
uint32_t crc32_update(uint32_t state,const void *data,uint32_t n);
int image_valid(const Image *h);
void flash_init(void);
uint32_t flash_id(void);
int flash_status(void);
int flash_erase(uint32_t a);
int flash_program(uint32_t a,const void *data,uint32_t n);
/* Loader area only (a < APP_FLASH); see src/loader_update.c. */
int flash_boot_erase(uint32_t a);
int flash_boot_program(uint32_t a,const void *data,uint32_t n);
#endif
