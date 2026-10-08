/* SPDX-License-Identifier: MIT */
#ifndef WIFI_WPA_CONSOLE_H
#define WIFI_WPA_CONSOLE_H
#include <stdint.h>
/* Copy-only hook, including inside SDIO command waits; never run RSN here. */
void wifi_wpa_radio_rx(const uint8_t *packet,unsigned length);
void wifi_wpa_uart_begin(uint32_t milliseconds);
/* Intercept before legacy command dispatch; nonzero means consume/discard. */
int wifi_wpa_uart_intercept(int byte,uint32_t milliseconds);
void wifi_wpa_uart_close(void);
void wifi_wpa_uart_info(void);
/* Explicit diagnostic association attempt; never reports WPA2/IP success. */
void wifi_wpa_uart_join(void);
struct wifi_ais_beacon;
int wifi_wpa_radio_validate(const uint8_t *own,const struct wifi_ais_beacon *);
unsigned wifi_wpa_radio_assoc_ie(uint8_t *,unsigned capacity);
#endif
