/* SPDX-License-Identifier: MIT */
#ifndef TUNER_TS_H
#define TUNER_TS_H
#include <stdint.h>
#define TUNER_TS_PACKET 188U
#define TUNER_TS_MAX_PACKETS 32U
/* UART task only; buffer holds at least max_packets*188 bytes.
 * Returns packet count, zero for no data, negative for bus/FIFO errors. */
int tuner_ts_read(uint8_t *buffer,unsigned max_packets);
int tuner_ts_classify(uint8_t status);
void tuner_ts_probe(void);
void tuner_ts_dma_probe(void);
void tuner_ts_dma_long_probe(void);
void tuner_ts_clock(void);
void tuner_ts_clock_max(void);
void tuner_ts_enable(void);
void tuner_ts_capture(void);
void tuner_ts_benchmark(void);
void tuner_ts_benchmark_receive(void);
void tuner_ts_stream_start(void);
void tuner_ts_stream_test_source(void);
void tuner_ts_stream_frame_size(void);
void tuner_ts_stream_burst(void);
void tuner_ts_stream_aggregate(void);
void tuner_ts_stream_pipeline(void);
void tuner_ts_stream_dma_source(void);
void tuner_ts_stream_dma_fixed(void);
void tuner_ts_stream_stop(void);
int tuner_ts_stream_active(void);
int tuner_ts_stream_aggregate_active(void);
/* Nonzero only when burst sending progressed without a stall/error. */
int tuner_ts_stream_poll(void);
void tuner_ts_stream_wifi_ticks(unsigned ticks);
void tuner_ts_stream_interrupt(void);
#endif
