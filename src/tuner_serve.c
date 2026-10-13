/* SPDX-License-Identifier: MIT. Same order as the former PC-driven UART sequence. */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "cache.h"
#include "sdio.h"
#include "tuner.h"
#include "tuner_ts.h"
#include "tuner_profile.h"
#include "tuner_uhf.h"
#include "tuner_serve.h"
void tuner_serve(void){
    uint8_t profile[32],v;
    uart_puts("SERVE start\n");
    /* Tuner first: the TS setup must precede the Wi-Fi radio start. */
    tuner_initialize();
    if(tuner_read_register(0x60,0xd6,&v) || !(v&1)){uart_puts("SERVE end status=tuner-not-calibrated\n");return;}
    TickType_t tuned=xTaskGetTickCount();
    if(tuner_uhf_profile(TUVL01_DEFAULT_CHANNEL,0,profile) || tuner_profile_apply(profile)!=TUNER_PROFILE_OK){
        uart_puts("SERVE end status=tune-failed\n");return;
    }
    /* The former sequence waited 6 s after tuning before configuring the TS path. */
    tuner_lock_wait(6000);
    while((TickType_t)(xTaskGetTickCount()-tuned)<pdMS_TO_TICKS(6000))vTaskDelay(1);
    tuner_ts_enable();
    tuner_ts_dma_probe();
    tuner_ts_clock_max();
    tuner_ts_dma_long_probe();
    instruction_cache_toggle();
    sdio_wifi_boot();
    sdio_wifi_clock();
    sdio_wifi_width();
    sdio_wifi_read_polling();
    sdio_wifi_write_polling();
    sdio_wifi_poll_budget();
    sdio_wifi_mac();
    sdio_wifi_capability();
    sdio_wifi_board();
    sdio_wifi_irq();
    /* Fast transmit configuration verified with full-segment TS. */
    tuner_ts_stream_pipeline();
    tuner_ts_stream_burst();
    tuner_ts_stream_aggregate();
    sdio_wifi_ap();
    uart_puts(sdio_wifi_ap_running()?"SERVE end status=ready\n":"SERVE end status=ap-failed\n");
}
