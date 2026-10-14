/* SPDX-License-Identifier: MIT */
#include "FreeRTOS.h"
#include "task.h"
void tuner_monitor_window_pause(unsigned milliseconds){
    vTaskDelay(pdMS_TO_TICKS(milliseconds));
}
