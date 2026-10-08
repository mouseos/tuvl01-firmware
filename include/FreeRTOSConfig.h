/* SPDX-License-Identifier: MIT */
#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H
#define configUSE_PREEMPTION 1
#define configUSE_TIME_SLICING 1
#define configCPU_CLOCK_HZ 216000000UL
#define configTICK_RATE_HZ 1000UL
#define configMAX_PRIORITIES 4
#define configMINIMAL_STACK_SIZE 256
#define configMAX_TASK_NAME_LEN 16
#define configTICK_TYPE_WIDTH_IN_BITS TICK_TYPE_WIDTH_32_BITS
#define configSUPPORT_STATIC_ALLOCATION 1
#define configSUPPORT_DYNAMIC_ALLOCATION 0
#define configUSE_TIMERS 0
#define configUSE_MUTEXES 0
#define configUSE_COUNTING_SEMAPHORES 0
#define configUSE_RECURSIVE_MUTEXES 0
#define configUSE_IDLE_HOOK 0
#define configUSE_TICK_HOOK 0
#define configCHECK_FOR_STACK_OVERFLOW 2
#define configUSE_TRACE_FACILITY 0
#define INCLUDE_vTaskDelay 1
#define INCLUDE_vTaskSuspend 1
#define INCLUDE_xTaskGetCurrentTaskHandle 1
void fault(void) __attribute__((noreturn));
#define configASSERT(x) do { if (!(x)) fault(); } while(0)
#endif
