/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "usb.h"
#include "image.h"
#include "sdio.h"
#include "sdio_irq.h"
#include "tuner.h"
#include "tuner_ts.h"
#include "tuner_profile.h"
#include "tuner_monitor.h"
#include "tuner_quality_watch.h"
#include "tuner_tmcc.h"
#include "cache.h"
#include "wifi_wpa_console.h"
#include "wifi_net.h"
#include "wifi_ctl.h"
#include "tuner_uhf.h"
#include "tuner_serve.h"
#include "loader_update.h"
#include "board_led.h"
extern void port_yield_entry(void),port_tick_entry(void),port_sdio_entry(void);
static void (*vectors[BOARD_VECTOR_COUNT])(void) __attribute__((aligned(1024)));
_Static_assert(BOARD_SDHI0_VECTOR<BOARD_VECTOR_COUNT,"SDHI0 vector outside table");
_Static_assert(BOARD_SDHI1_VECTOR<BOARD_VECTOR_COUNT,"SDHI1 vector outside table");
static StaticTask_t idle_tcb,log_tcb,usb_tcb;
static StackType_t idle_stack[256],log_stack[512],usb_stack[2048];
static unsigned audit_active,audit_pos;
static uint32_t audit_crc;
void vApplicationGetIdleTaskMemory(StaticTask_t **t,StackType_t **s,uint32_t *n) { *t=&idle_tcb;*s=idle_stack;*n=256; }
void vApplicationStackOverflowHook(TaskHandle_t t,char *n) { (void)t;(void)n;fault(); }
static void log_task(void *p) {
    (void)p;
    for (;;) {
        /* A higher-priority command task must not splice its response into
         * this line. Scheduler suspension leaves timer interrupts enabled. */
        vTaskSuspendAll();
        uart_puts("RTOS tick=");uart_hex(xTaskGetTickCount());uart_puts("\n");
        xTaskResumeAll();vTaskDelay(1000);
    }
}
static int stream_service_wait(TickType_t now,TickType_t slice_start,int progress){
    return !progress || (TickType_t)(now-slice_start)>=pdMS_TO_TICKS(4);
}
static void usb_task(void *p) {
    (void)p;
    usb_init();
    board_led_init();
    TickType_t slice_start=xTaskGetTickCount(),lock_at=slice_start;
#ifdef TUVL01_AUTOSERVE
    /* Standalone image (make AUTOSERVE=1): come up serving without any PC. */
    tuner_serve();
    slice_start=lock_at=xTaskGetTickCount();
#endif
    for (;;) {
        sdio_wifi_service_mark(0);
        usb_poll();int c=uart_getc();
        if(wifi_wpa_uart_intercept(c,xTaskGetTickCount())){
            /* Drain available binary input; a 1ms delay per byte would
             * overflow the UART FIFO at 115200 baud. Yield when empty. */
            if(c<0)vTaskDelay(1);
            continue;
        }
        /* Wi-Fi control clients start/stop the stream through the same commands. */
        if(c<0)c=wifi_ctl_poll(xTaskGetTickCount(),pdMS_TO_TICKS(5000));
        if(c<0){
            unsigned tune_channel,tune_partial;
            if(wifi_ctl_take_tune(&tune_channel,&tune_partial)){
                /* The stream cannot follow a retune: stop it, tune, and let the client start again. */
                uint8_t profile[32];
                if(tuner_ts_stream_active())tuner_ts_stream_stop();
                int ok=!tuner_uhf_profile(tune_channel,tune_partial,profile) && tuner_profile_apply(profile)==TUNER_PROFILE_OK;
                /* A new frame lock takes a while; START is refused before it, so wait for it here. */
                unsigned locked=ok && tuner_lock_wait(4000);
                uart_puts(ok?(locked?"TUNE wifi end status=locked\n":"TUNE wifi end status=no-lock\n"):"TUNE wifi end status=failed\n");
                wifi_ctl_tune_done(ok);
                if(ok)wifi_ctl_set_lock(locked);
            }else{
                TickType_t lock_now=xTaskGetTickCount();
                if(wifi_ctl_client_seen() && (TickType_t)(lock_now-lock_at)>=pdMS_TO_TICKS(1000)){
                    uint8_t sync;
                    lock_at=lock_now;
                    /* Stable frame lock: the same criterion as the UART TMCC read. */
                    if(!tuner_read_register(0x61,0x97,&sync))wifi_ctl_set_lock((sync&0x18)==0x10);
                }
            }
        }
        if(c>=0 && c!='i' && c!='|' && c!=13 && c!=18 && c!=20 && c!=21 && c!=22 && c!=24)sdio_wifi_tx_bench_stop();
        if(c>=0 && c!=13 && c!=18 && c!=20 && c!=21 && c!=22 && c!=24 && c!='i' && c!='|' && c!='t' && c!='B' && c!='E' && c!='7' && c!='5' && c!='4' && c!='^')tuner_ts_stream_interrupt();
        if(c=='u')usb_debug();
        if(c=='g')usb_pin_debug();
        if(c=='d')sdio_identify();
        if(c=='h')sdio_wifi_boot();
        if(c=='|')sdio_wifi_restart();
        if(c=='m')sdio_wifi_mac();
        if(c=='n')sdio_wifi_capability();
        if(c=='c')sdio_wifi_scan();
        if(c=='}')sdio_wifi_ais_channel_probe();
        if(c=='{')sdio_wifi_ais_auth_probe();
        if(c=='"')sdio_wifi_ais_assoc_probe();
        if(c=='(')sdio_wifi_ais_connect_probe();
        if(c==2)wifi_wpa_uart_begin(xTaskGetTickCount());
        if(c==3)wifi_wpa_uart_close();
        if(c==4)wifi_wpa_uart_join();
        if(c=='b')sdio_wifi_board();
        if(c==6)sdio_wifi_osc();
        if(c=='a')sdio_wifi_ap();
        if(c=='x')sdio_wifi_ap_stop();
        if(c=='t')sdio_wifi_stats();
        if(c=='L')sdio_wifi_read_polling();
        if(c=='Y')sdio_wifi_write_polling();
        if(c=='N')sdio_wifi_ts_feedback();
        if(c=='O')sdio_wifi_nic_stats();
        if(c=='K')sdio_wifi_link();
        if(c=='R')sdio_wifi_rate();
        if(c=='Z')sdio_wifi_poll_reuse();
        if(c=='A')sdio_wifi_status_poll();
        if(c=='G')sdio_wifi_poll_budget();
        if(c=='X')sdio_wifi_irq();
        if(c=='9')sdio_wifi_tx_window();
        if(c=='8')sdio_wifi_queue();
        if(c=='7')tuner_ts_stream_test_source();
        if(c==9)tuner_ts_stream_pipeline();
        if(c==11)tuner_ts_stream_dma_source();
        if(c==12)tuner_ts_stream_dma_fixed();
        if(c=='6')sdio_wifi_station_stats();
        if(c=='5')tuner_ts_stream_frame_size();
        if(c=='4')sdio_wifi_tx_timing();
        if(c=='3')sdio_wifi_rate_profile();
        if(c=='2')sdio_wifi_cam();
        if(c=='1')sdio_wifi_radio_debug();
        if(c=='!')sdio_wifi_radio_groups();
        if(c=='0')sdio_wifi_channel();
        if(c=='?')sdio_wifi_channel_bssid();
        if(c=='%')sdio_wifi_ht();
        if(c=='^')sdio_wifi_io_timing();
        if(c=='~')sdio_wifi_raw_tx();
        if(c==':')sdio_wifi_qos_tx();
        if(c==';')sdio_wifi_qos_class();
        if(c=='/')sdio_wifi_fixed_mcs();
        if(c==7)sdio_wifi_tx_bench_size();
        if(c==8)sdio_wifi_tx_bench_burst();
        if(c=='<')sdio_wifi_tx_bench_start();
        if(c=='>')sdio_wifi_tx_bench_stop();
        if(c=='[')sdio_wifi_more_data();
        if(c==']')sdio_wifi_credit_probe();
        if(c=='@')sdio_wifi_dpd();
        if(c=='&')sdio_wifi_rate_mailbox();
        if(c=='$')sdio_wifi_auto_per();
        if(c=='=')sdio_wifi_rx_sink_start();
        if(c=='_')sdio_wifi_rx_sink_stop();
        if(c=='+')sdio_wifi_rx_sink_stats();
        if(c=='S')tuner_ts_stream_burst();
        if(c=='U')tuner_ts_stream_aggregate();
        if(c=='P')sdio_wifi_read_check();
        if(c=='v')sdio_wifi_verbose();
        if(c=='k')sdio_wifi_clock();
        if(c==20)sdio_wifi_clock_profile();
        if(c==21)sdio_wifi_idle_sample(tuner_quality);
        if(c=='W')sdio_wifi_width();
        if(c=='e')tuner_probe();
        if(c=='j')tuner_board_probe();
        if(c=='o')tuner_analog();
        if(c=='p')tuner_initialize();
        if(c=='s')tuner_ts_probe();
        if(c=='D')tuner_ts_dma_probe();
        if(c=='H')tuner_ts_benchmark();
        if(c==5)tuner_ts_benchmark_receive();
        if(c=='C')tuner_ts_clock();
        if(c=='J')tuner_ts_clock_max();
        if(c=='I')instruction_cache_toggle();
        if(c=='T')tuner_ts_dma_long_probe();
        if(c==18)tuner_ts_state();
        if(c=='z')tuner_ts_enable();
        if(c=='w')tuner_profile_receive();
        if(c==22)tuner_profile_switch();
        if(c=='y')tuner_monitor();
        if(c=='M')tuner_fec_snapshot();
        if(c=='Q')tuner_quality();
        if(c==13)tuner_quality_watch_start();
        if(c==14)tuner_quality_watch_dump();
        if(c==15)sdio_wifi_tx_power();
        if(c==17)sdio_wifi_tx_ampdu();
        if(c=='l')tuner_ts_capture();
        if(c==23)tuner_ts_capture_poll();
        if(c==24)sdio_wifi_quiet_sample(tuner_quality);
        if(c==25)tuner_rf_switch();
        if(c==26)tuner_reg_access();
        if(c==1)tuner_program_port_probe();
        if(c=='*')tuner_program_burst_probe();
        if(c=='.')tuner_program_release_probe();
        if(c==127)tuner_program_restart_probe();
        if(c==128)tuner_program_address_probe();
        if(c==129)tuner_program_mailbox_probe();
        if(c==130)tuner_program_mailbox_sweep();
        if(c==131)tuner_monitor_window_probe();
        if(c==132)tuner_program_mailbox_select();
        if(c==133)tuner_monitor_window_updates();
        if(c==134)tuner_monitor_window_timing();
        if(c==135)tuner_d4_window_halted();
        if(c==136)tuner_program_mailbox_d5();
        if(c==137)tuner_program_mailbox_d5_write20();
        if(c==138)tuner_program_mailbox_reference_select();
        if(c=='`')tuner_pin_capture_probe();
        if(c=='-')tuner_pin_test_probe();
        if(c==',')tuner_pin_gpio_selftest();
        if(c==27)tuner_gpio_dump();
        if(c==28)tuner_gpio_drive();
        if(c==29)tuner_gpio_release();
        if(c==30)tuner_ts_group_bench();
        if(c==31)sdio_wifi_tim();
        if(c==16)tuner_serve();
        if(c==19)loader_update_command();
        if(c==10)board_led_command();
        if(c=='B')tuner_ts_stream_start();
        if(c=='E')tuner_ts_stream_stop();
        if(c=='r')tuner_tmcc_read();
        if(c=='F')tuner_band_base(8);
        if(c=='V')tuner_band_base(4);
        sdio_wifi_service_mark(1);
        TickType_t poll_begin=xTaskGetTickCount();
        sdio_wifi_poll();
        sdio_wifi_tx_bench_poll();
        tuner_ts_stream_wifi_ticks((TickType_t)(xTaskGetTickCount()-poll_begin));
        {
            TickType_t led_now=xTaskGetTickCount();
            board_led_service(led_now,tuner_ts_stream_active() || wifi_ctl_client_alive(led_now,pdMS_TO_TICKS(5000)));
        }
        sdio_wifi_service_mark(2);
        int stream_progress=tuner_ts_stream_poll();
        tuner_quality_watch_poll();
        sdio_wifi_service_mark(3);
        if(c=='i'){uart_puts("UART application\n");wifi_wpa_uart_info();}
        if(c=='f'){audit_active=1;audit_pos=0;audit_crc=UINT32_MAX;}
        if(c=='q'){usb_request(0x40,8,0,0,0,0);usb_idle();}
        if(audit_active){
            uint8_t data[64];
            if(flash_read(audit_pos,data,sizeof data)){
                audit_active=0;uart_puts("NOR protected read failed\n");
            } else {
                audit_crc=crc32_update(audit_crc,data,sizeof data);audit_pos+=sizeof data;
                if(audit_pos==APP_FLASH){
                    audit_active=0;uart_puts("NOR protected_crc=");uart_hex(~audit_crc);uart_puts("\n");
                }
            }
        }
        sdio_wifi_service_mark(4);
        /* Revisit USB/UART and radio service between each TS batch. Yield
         * on a stall or after four ticks, including tick counter wrap. */
        if(stream_service_wait(xTaskGetTickCount(),slice_start,stream_progress)){
            vTaskDelay(1);slice_start=xTaskGetTickCount();
        }
        sdio_wifi_service_mark(5);
    }
}
static unsigned recover;
int usb_request(unsigned type,unsigned req,unsigned value,unsigned index,unsigned length,unsigned char *reply) {
    if(type==0xc0 && req==1 && !value && !index && length==32){
        uint32_t info[8]={0x5455564c,1,0,xTaskGetTickCount(),0,0,0,0x41505031};
        for(unsigned i=0;i<32;i++)reply[i]=((unsigned char *)info)[i];
        return 32;
    }
    if(type==0x40 && req==8 && !value && !index && !length){recover=1;return 0;}
    return -1;
}
int usb_out(const unsigned char *p,unsigned n){(void)p;(void)n;return -1;}
void usb_idle(void){
    if(!recover)return;
    wifi_wpa_uart_close();
    /* Stop with the live application's channel token and peer record before
     * disabling RTOS ticks: SDIO deadlines require those ticks to advance.
     * A failed radio cleanup must still allow UART recovery. */
    tuner_ts_stream_interrupt();
    sdio_wifi_quiesce();
    sdio_irq_set(0);
    portDISABLE_INTERRUPTS();
    if(instruction_cache_set(0))fault();
    R16(0xfffec000)&=(uint16_t)~1;
    usb_detach();
    for(volatile unsigned n=0;n<2000000;n++){}
    ((void (*)(void))0xfff80000UL)();
    fault();
}
void firmware_main(void) {
    board_init();
    uart_puts("TUVL01 independent / FreeRTOS 11.1.0 / GNU SH2A BE\n");
    uart_puts("Application revision=168\n");
#ifdef TUVL01_AUTOSERVE
    uart_puts("Build variant=standalone (serves on start)\n");
#else
    uart_puts("Build variant=development (waits for UART commands)\n");
#endif
    wifi_net_service=wifi_ctl_service;
    flash_init(); /* Read-only NOR diagnostics; write routines are not referenced. */
    for (unsigned i=0;i<BOARD_VECTOR_COUNT;i++) vectors[i]=fault;
    vectors[33]=port_yield_entry;
    vectors[171]=port_tick_entry;
    vectors[BOARD_SDHI0_VECTOR]=port_sdio_entry;
    uintptr_t v=(uintptr_t)vectors;
    __asm__ volatile("ldc %0,vbr" :: "r"(v) : "memory");
    configASSERT(xTaskCreateStatic(log_task,"uart",512,0,1,log_stack,&log_tcb));
    configASSERT(xTaskCreateStatic(usb_task,"usb",sizeof usb_stack/sizeof usb_stack[0],0,2,usb_stack,&usb_tcb));
    vTaskStartScheduler();
    fault();
}
