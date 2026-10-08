/* SPDX-License-Identifier: MIT */
#ifndef WIFI_SERVICE_TIMING_H
#define WIFI_SERVICE_TIMING_H
#include "wifi_io_timing.h"
struct wifi_service_timing {
    struct wifi_io_timing phases,loops;
    uint32_t last,stage,open,loop_begin,stalls_begin,tx_begin,stalled,sent,invalid;
};
void wifi_service_start(struct wifi_service_timing *s,uint32_t now);
void wifi_service_stop(struct wifi_service_timing *s,uint32_t now);
/* 0 loop start, 1 front end done, 2 Wi-Fi done, 3 TS done,
 * 4 other work done, 5 delay done. Counter deltas cover TS only. */
void wifi_service_mark(struct wifi_service_timing *s,unsigned mark,uint32_t now,uint32_t stalls,uint32_t tx);
#endif
