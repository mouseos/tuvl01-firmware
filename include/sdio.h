/* SPDX-License-Identifier: MIT */
#ifndef SDIO_H
#define SDIO_H
void sdio_identify(void);
void sdio_wifi_boot(void);
/* Explicit MT5931 SDIO reset + vendor firmware reload; refuses active traffic. */
void sdio_wifi_restart(void);
void sdio_wifi_mac(void);
void sdio_wifi_capability(void);
void sdio_wifi_scan(void);
void sdio_wifi_board(void);
/* Explicit idle-only MT5931 oscillator stable-time0 command; no readback. */
void sdio_wifi_osc(void);
void sdio_wifi_dpd(void);
void sdio_wifi_auto_per(void);
void sdio_wifi_ap(void);
void sdio_wifi_ap_stop(void);
/* Best effort before RAM handoff; failure must not prevent recovery. */
void sdio_wifi_quiesce(void);
void sdio_wifi_poll(void);
void sdio_wifi_stats(void);
void sdio_wifi_nic_stats(void);
void sdio_wifi_station_stats(void);
void sdio_wifi_link(void);
void sdio_wifi_rate(void);
void sdio_wifi_cam(void);
void sdio_wifi_radio_debug(void);
void sdio_wifi_rate_mailbox(void);
void sdio_wifi_radio_groups(void);
void sdio_wifi_rate_profile(void);
void sdio_wifi_channel(void);
void sdio_wifi_tx_power(void);
/* Explicit selected AP only; bounded AIS JOIN lease probe, always released. */
void sdio_wifi_ais_channel_probe(void);
void sdio_wifi_ais_auth_probe(void);
/* Finite association trial: host state2, no keys/data/state3; always cleans up. */
void sdio_wifi_ais_assoc_probe(void);
/* Finite state3 + new-beacon/PM trial; no keys or IP data; always cleans up. */
void sdio_wifi_ais_connect_probe(void);
struct wifi_ais_beacon;
/* Copy validated completed-scan target only; no radio state change. */
int sdio_wifi_wpa_select(unsigned channel,const unsigned char *ap,
    unsigned char *own,struct wifi_ais_beacon *selected);
void sdio_wifi_channel_bssid(void);
void sdio_wifi_ht(void);
void sdio_wifi_fixed_mcs(void);
void sdio_wifi_more_data(void);
void sdio_wifi_tx_bench_size(void);
void sdio_wifi_tx_bench_burst(void);
void sdio_wifi_tx_bench_start(void);
void sdio_wifi_tx_bench_stop(void);
void sdio_wifi_tx_bench_poll(void);
void sdio_wifi_rx_sink_start(void);
void sdio_wifi_rx_sink_stop(void);
void sdio_wifi_rx_sink_stats(void);
void sdio_wifi_raw_tx(void);
void sdio_wifi_qos_tx(void);
void sdio_wifi_qos_class(void);
unsigned sdio_wifi_qos_class_selected(void);
unsigned sdio_wifi_raw_tx_selected(void);
void sdio_wifi_io_timing(void);
void sdio_wifi_io_start(void);
void sdio_wifi_service_mark(unsigned mark);
/* Exclude outstanding timing sample before stream-stop UART output. */
void sdio_wifi_ts_timing_stop(void);
void sdio_wifi_poll_reuse(void);
void sdio_wifi_status_poll(void);
void sdio_wifi_credit_probe(void);
void sdio_wifi_poll_budget(void);
void sdio_wifi_irq(void);
void sdio_wifi_tx_window(void);
void sdio_wifi_queue(void);
void sdio_wifi_read_check(void);
void sdio_wifi_read_polling(void);
void sdio_wifi_write_polling(void);
void sdio_wifi_ts_feedback(void);
void sdio_wifi_tx_timing(void);
void sdio_wifi_verbose(void);
void sdio_wifi_clock(void);
void sdio_wifi_width(void);
int sdio_wifi_ts(const unsigned char *data,unsigned count,unsigned sequence,unsigned index,unsigned flags);
/* Return packets submitted (1..14), zero for credit stall, negative on fault. */
int sdio_wifi_ts_pair(const unsigned char *data,unsigned count,unsigned sequence,unsigned index,unsigned flags);
/* Security HIF submission, only for the activated selected AIS peer.
 * Success means accepted SDIO transfer, never over-air delivery/key install. */
int sdio_wifi_wpa_eapol_submit(unsigned port,unsigned tc,const unsigned char *,unsigned length);
/* Initial CCMP only, zero RSC. Zero means command transfer/credit return,
 * not hardware key application. Uncertain submission blocks later commands. */
int sdio_wifi_wpa_key_submit(const unsigned char *body,unsigned length);
/* Internal lifecycle API: explicit selected target7 (channel+AP), retains
 * BSS/station after releasing JOIN privilege. Association is not WPA2/IP. */
int sdio_wifi_wpa_join(const unsigned char *target);
int sdio_wifi_wpa_leave(void);
unsigned sdio_wifi_milliseconds(void);
#endif
