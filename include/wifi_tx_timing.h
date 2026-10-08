/* SPDX-License-Identifier: MIT */
#ifndef WIFI_TX_TIMING_H
#define WIFI_TX_TIMING_H
#include <stdint.h>
struct wifi_tx_time_bin {
    uint32_t credits,credit_sum,credit_min,credit_max,writes,write_sum;
    uint32_t done,done_sum,done_min,done_max,done_failed;
    uint32_t poll_sum,poll_min,poll_max,poll_gap_max;
};
struct wifi_tx_timing {
    struct wifi_tx_time_bin bin[7];
    uint32_t active,packets,start,excluded;
    uint32_t polls,last_poll,poll_gap;
    uint8_t sample_packets[128];
    uint32_t sample_start[128];
};
void wifi_tx_timing_reset(struct wifi_tx_timing *s);
void wifi_tx_timing_begin(struct wifi_tx_timing *s,unsigned packets,uint32_t now);
void wifi_tx_timing_written(struct wifi_tx_timing *s,uint32_t now);
void wifi_tx_timing_credit(struct wifi_tx_timing *s,unsigned free,uint32_t now);
void wifi_tx_timing_poll(struct wifi_tx_timing *s,uint32_t now);
void wifi_tx_timing_other(struct wifi_tx_timing *s);
void wifi_tx_timing_sample(struct wifi_tx_timing *s,uint8_t tag,unsigned packets,uint32_t now);
void wifi_tx_timing_done(struct wifi_tx_timing *s,uint8_t tag,uint8_t status,uint32_t now);
void wifi_tx_timing_cancel(struct wifi_tx_timing *s,uint8_t tag);
#endif
