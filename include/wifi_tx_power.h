#ifndef WIFI_TX_POWER_H
#define WIFI_TX_POWER_H
#include <stdint.h>
/* Prefix is filled by the HIF command sender. Offset is in half-dBm units. */
int wifi_tx_power_command(uint8_t *packet,unsigned capacity,int offset);
#endif
