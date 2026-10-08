/* SPDX-License-Identifier: MIT */
#ifndef WIFI_IO_TIMING_H
#define WIFI_IO_TIMING_H
#include <stdint.h>
enum wifi_io_kind {WIFI_IO_WHISR,WIFI_IO_WTSR,WIFI_IO_RX_LENGTH,WIFI_IO_OTHER_READ,WIFI_IO_RX_FIFO,WIFI_IO_TS_WRITE,WIFI_IO_SNAPSHOT,WIFI_IO_KINDS};
struct wifi_io_bin {uint32_t calls,ticks,minimum,maximum,requested_bytes,failed,overflow;};
struct wifi_io_timing {uint32_t active,start,duration;struct wifi_io_bin bin[WIFI_IO_KINDS];};
unsigned wifi_io_read_kind(unsigned address);
void wifi_io_start(struct wifi_io_timing *s,uint32_t now);
void wifi_io_stop(struct wifi_io_timing *s,uint32_t now);
void wifi_io_record(struct wifi_io_timing *s,unsigned kind,unsigned requested_bytes,uint32_t begin,uint32_t end,int failed);
#endif
