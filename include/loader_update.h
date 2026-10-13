/* SPDX-License-Identifier: MIT */
#ifndef LOADER_UPDATE_H
#define LOADER_UPDATE_H
#include <stdint.h>
/* The boot ROM copies the first 8 KiB of the SPI NOR to RAM and runs it: that is
 * the loader. This rewrites exactly those two 4 KiB sectors. */
#define LOADER_SIZE 8192U
#define LOADER_BANNER "TUVL01 independent recovery boot"
enum {LOADER_OK=0,LOADER_BAD_CRC=-1,LOADER_BAD_IMAGE=-2,LOADER_FLASH_ID=-3,LOADER_PROTECTED=-4,
      LOADER_ERASE=-5,LOADER_PROGRAM=-6,LOADER_VERIFY=-7};
/* Accepts only an 8 KiB image whose CRC32 matches and that contains the loader banner. */
int loader_image_check(const uint8_t *image,uint32_t crc);
/* Refuses when the NOR reports block protection. Writes sector 1, verifies it, then
 * sector 0, verifies it. Returns LOADER_OK or the first failure; a failure before the
 * sector 0 erase leaves the existing loader untouched. */
int loader_update_apply(const uint8_t *image);
/* UART task: receives 8192+4 bytes in acknowledged 64-byte chunks and applies them. */
void loader_update_command(void);
#endif
