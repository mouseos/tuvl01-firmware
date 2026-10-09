/* SPDX-License-Identifier: MIT. Independent, polling-only SDIO identification.
 * Register accesses checked against SH726A board initialization/command code.
 * No Linux/stock MCU code. Optional board radio blob is supplied at runtime. */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "sdio.h"
#include "sdio_irq.h"
#include "image.h"
#include "wifi_board.h"
#include "wifi_mgmt.h"
#include "wifi_hif.h"
#include "wifi_net.h"
#include "wifi_rx_sink.h"
static struct wifi_rx_sink wifi_sink;
static unsigned wifi_sink_active;
static unsigned wifi_more_data;
static unsigned wifi_bench_active,wifi_bench_sent,wifi_bench_stalls,wifi_bench_failed;
static uint32_t wifi_bench_begin;
static uint8_t wifi_bench_body[1472];
static unsigned wifi_bench_size=1332,wifi_bench_burst=1;
static uint32_t wifi_sink_begin,wifi_sink_end;
#include "wifi_tx_feedback.h"
#include "wifi_statistics.h"
#include "wifi_link.h"
#include "wifi_fw_query.h"
#include "tuner_ts.h"
#include "wifi_tx_timing.h"
#include "wifi_channel.h"
#include "wifi_rates.h"
#include "wifi_ht.h"
#include "wifi_fixed_rate.h"
#include "wifi_io_timing.h"
#include "time_counts.h"
#include "wifi_service_timing.h"
#include "wifi_raw_tx.h"
#include "wifi_power_events.h"
#include "wifi_station.h"
#include "wifi_ais_beacon.h"
#include "wifi_scan.h"
#include "wifi_scan_cache.h"
#include "wifi_ais_join.h"
#include "wifi_wpa_console.h"
static struct wifi_ais_join wifi_ais_connection;
#include "wifi_ais_rsn.h"
static struct wifi_scan_cache wifi_bss_cache;
#include "wifi_ais_mgmt.h"
static struct wifi_power_events wifi_power;
static struct wifi_tx_timing wifi_timing;
static unsigned wifi_timing_enabled;
#include "wifi_ts_tx.h"
#include "wifi_status.h"
#include "wifi_queue.h"
extern const uint32_t wifi_radio_descriptor[];
extern const uint8_t wifi_radio_bytes[],wifi_radio_end[];
#define S(o) R16(0xffffc800UL+(o))
static unsigned card_verified;
static unsigned wifi_read_fast;
static unsigned wifi_write_fast;
static unsigned wifi_poll_budget=64,wifi_wait_spins,wifi_wait_yields;
static unsigned wifi_status_polling,wifi_status_reads;
static uint32_t wifi_status_rx;
static unsigned wifi_feedback_enabled;
static unsigned wifi_ts_window=14,wifi_window_stalls;
static unsigned wifi_queue_mode;
static struct wifi_tx_feedback wifi_feedback;
static unsigned wifi_idle_deferred,wifi_idle_polls;
static uint8_t wifi_sequence;
static unsigned wifi_beacons,wifi_scan_active,wifi_scan_unresolved;
static unsigned wifi_hif_ready;
static unsigned wifi_tc4_free,wifi_tx_fault;
static unsigned wifi_connection_unresolved,wifi_ais_cam_attempted,wifi_ais_cam_transferred;
static unsigned wifi_ais_retained_active,wifi_ais_retained_teardown;
static unsigned wifi_tc1_free,wifi_tc2_free,wifi_tc3_free,wifi_tc5_free;
static uint8_t wifi_data[4][1514];
static unsigned wifi_data_lengths[4],wifi_data_head,wifi_data_count;
static unsigned wifi_verbose,wifi_data_rx,wifi_data_tx,wifi_data_dropped;
static uint8_t wifi_management_rcpi,wifi_peer_rcpi;
static uint8_t wifi_mac[6];
static unsigned wifi_mac_valid,wifi_board_sent,wifi_ap_active;
static unsigned wifi_dpd_attempted,wifi_dpd_transferred;
static unsigned wifi_osc_attempted;
static unsigned wifi_per_attempted,wifi_per_transferred,wifi_per_steps;
static uint8_t wifi_management[512];
static unsigned wifi_management_length;
static uint16_t wifi_management_sequence;
static uint8_t wifi_management_tx_sequence;
/* Previous development applications used token1 and could leave its channel
 * privilege behind when replacing only the MCU RAM application. */
static uint8_t wifi_channel_token=1;
static unsigned wifi_ap_stop_ok;
static uint8_t wifi_peer[6],wifi_ap_bss[88];
static unsigned wifi_peer_state,wifi_peer_active,wifi_peer_activated,wifi_peer_activate_pending;
static uint16_t wifi_peer_rates=0x3fcf,wifi_peer_listen=1;
static unsigned wifi_fixed54,wifi_fixed_mcs;
static unsigned wifi_rate_profile;
static unsigned wifi_ht_enabled;
static unsigned wifi_io_enabled;
static unsigned wifi_raw_tx_mode,wifi_qos_tc=1;
static struct wifi_io_timing wifi_io;
static struct wifi_service_timing wifi_service;
/* Direct UDP benchmark: kind0 is SDIO write, kind1 is the complete
 * single-outstanding-credit interval. Neither proves over-air delivery. */
static struct wifi_io_timing wifi_bench_io;
static uint32_t wifi_bench_credit_begin;
static unsigned wifi_bench_credit_pending,wifi_bench_credit_excluded;
static void bench_credit_other(void){
    if(wifi_bench_credit_pending){wifi_bench_credit_pending=0;++wifi_bench_credit_excluded;}
}
static void bench_credit_returned(unsigned released){
    if(wifi_bench_io.active && wifi_bench_credit_pending && released && wifi_tc1_free==14){
        wifi_io_record(&wifi_bench_io,1,wifi_bench_size,wifi_bench_credit_begin,board_time_counts(),0);
        wifi_bench_credit_pending=0;
    }
}
static uint32_t wifi_io_yields_begin,wifi_io_irq_begin,wifi_io_ready_begin;
static uint32_t wifi_io_yields,wifi_io_irq_waits,wifi_io_irq_ready;
static struct wifi_ht_peer wifi_peer_ht;
static unsigned wifi_ap_channel=1;
static unsigned wifi_channel_bssid_mode;
static unsigned wifi_poll_reuse,wifi_credit_fresh,wifi_poll_count,wifi_reuse_count;
static unsigned wifi_credit_probe,wifi_probe_reads,wifi_probe_released;
static unsigned wifi_management_pending,wifi_management_done,wifi_management_result;
static TickType_t wifi_management_start,wifi_peer_activate_start;
static uint8_t wifi_management_pending_sequence;
static int control_send(unsigned cid,unsigned set,uint8_t *packet,unsigned length);
static int control_set(unsigned cid,uint8_t *packet,unsigned length);
static int event_read(uint8_t *packet,unsigned capacity,unsigned *length);
static uint32_t swap32(uint32_t n){return (n>>24)|((n>>8)&0xff00)|((n<<8)&0xff0000)|(n<<24);}
static void field(const char *s,uint32_t n){uart_puts(s);uart_hex(n);}
static void status(void){
    field(" INFO1=",S(0x1c));field(" INFO2=",S(0x1e));
    field(" CLK=",S(0x24));field(" OPTION=",S(0x28));uart_puts("\n");
}
static void host_init(void){
    wifi_scan_cache_finish(&wifi_bss_cache,0);
    sdio_irq_set(0);
    R8(0xfffe0408)&=(uint8_t)~0x18;(void)R8(0xfffe0408);
    S(0xe0)=0;S(0xe0)=1;
    /* Mask all host interrupts: the independent application polls status. */
    S(0x20)=0x03bd;S(0x22)=0x837f;
    S(0x38)=0xc007;S(0x34)=0;S(0x36)=0;
    S(0x1c)&=(uint16_t)~5;S(0x1e)=0;
    S(0x28)=0x80ae;S(0xf0)=0xc0;
    R16(0xfffe3868)=0x2222;R16(0xfffe386a)=0x2222;
    S(0x24)=0x0180; /* Stock CMD5 probe setting, one-bit bus. */
    vTaskDelay(10);
}
/* Independent opt-in read/write comparisons use bounded short polling before
 * yielding a tick. Both default to the proven slow cadence. RX FIFO block
 * waits remain unchanged; neither selector alters bus clock or width. */
static void read_wait(unsigned *polls,unsigned fast){
    if(fast && ++*polls<wifi_poll_budget){wifi_wait_spins++;return;}
    wifi_wait_yields++;
    *polls=0;vTaskDelay(1);
}
static int transfer_wait(unsigned *polls,unsigned fast,unsigned info1,unsigned info2,
                         TickType_t start,TickType_t limit){
    if(sdio_irq_enabled()){
        TickType_t elapsed=(TickType_t)(xTaskGetTickCount()-start);
        if(elapsed>=limit || sdio_irq_wait(info1,info2,limit-elapsed)){
            uart_puts("SDIO IRQ wait timeout\n");status();return -1;
        }
    }else read_wait(polls,fast);
    return 0;
}
/* Mode2 tests the Renesas SDHI idle-wait contract before command/config
 * writes. INFO2 bit13 is high in the measured idle state; compatible TMIO
 * controllers call it SCLKDIVEN, with CBSY at bit14. Exact SH726A semantics
 * are not publicly specified, so this remains an explicit comparison mode. */
static int bus_idle(void){
    if(wifi_read_fast!=2)return 0;
    unsigned polls=0,deferred=0;TickType_t start=xTaskGetTickCount();
    for(;;){
        unsigned info=S(0x1e);
        if((info&0x6000)==0x2000)return 0;
        if(!deferred){wifi_idle_deferred++;deferred=1;}
        wifi_idle_polls++;
        if((TickType_t)(xTaskGetTickCount()-start)>=100){
            uart_puts("SDIO idle wait timeout");status();return -1;
        }
        read_wait(&polls,1);
    }
}
static int command(uint16_t cmd,uint32_t arg,uint32_t *response){
    if(bus_idle())return -1;
    S(0x1c)&=(uint16_t)~1;S(0x1e)&=0x7f80;
    S(4)=(uint16_t)arg;S(6)=(uint16_t)(arg>>16);S(0)=cmd;
    unsigned polls=0;TickType_t start=xTaskGetTickCount();
    for(;;){
        unsigned info1=S(0x1c),info2=S(0x1e);
        if(info2&0x807f){field("SDIO command error cmd=",cmd);status();return -1;}
        if(info1&1){
            *response=(uint32_t)S(0xc)|((uint32_t)S(0xe)<<16);
            S(0x1c)&=(uint16_t)~1;return 0;
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=100){
            field("SDIO command timeout cmd=",cmd);status();return -1;
        }
        unsigned fast=cmd&0x1000?(wifi_read_fast==1 || wifi_read_fast==2 || wifi_read_fast==3):
            ((cmd==0x4c35 || cmd==0x6c35) && (wifi_write_fast==1 || wifi_write_fast==3));
        if(transfer_wait(&polls,fast,1,0,start,100))return -1;
    }
}
static int direct(unsigned function,uint32_t address,uint8_t *value,int write){
    if(function>7 || address>0x1ffff)return -1;
    uint32_t r;
    uint32_t arg=(function<<28)|(address<<9);
    if(write)arg|=0x80000000UL|*value;
    if(command(write?0x4434:0x5434,arg,&r))return -1;
    if(r&0xcb00){field("SDIO R5 error=",r);uart_puts("\n");return -1;}
    *value=(uint8_t)r;return 0;
}
static int read_byte(uint32_t address,uint8_t *value){return direct(0,address,value,0);}
static int extended_word(uint32_t address,uint32_t *raw){
    if(address>0x1fffc)return -1;
    if(bus_idle())return -1;
    S(0x26)=4;S(8)=0;
    S(0x1c)&=(uint16_t)~4;S(0x1e)&=(uint16_t)~0x100;
    uint32_t response;
    /* Stock byte-mode CMD53 read; function1, incrementing address, 4 bytes. */
    if(command(0x5c35,0x14000004UL|(address<<9),&response))return -1;
    if(response&0xcb00){field("SDIO CMD53 R5 error=",response);uart_puts("\n");return -1;}
    unsigned polls=0;TickType_t start=xTaskGetTickCount();unsigned received=0;
    for(;;){
        unsigned info1=S(0x1c),info2=S(0x1e);
        if(info2&0x807f){uart_puts("SDIO CMD53 data error");status();return -1;}
        if(!received && (info2&0x100)){
            S(0x1e)&=(uint16_t)~0x100;
            *raw=R32(0xffffc830UL);received=1;
        }
        if(received && (info1&4)){S(0x1c)&=(uint16_t)~4;return 0;}
        if((TickType_t)(xTaskGetTickCount()-start)>=1000){
            uart_puts("SDIO CMD53 data timeout");status();return -1;
        }
        if(transfer_wait(&polls,wifi_read_fast==1 || wifi_read_fast==2 || wifi_read_fast==4,
            received?4:0,received?0:0x100,start,1000))return -1;
    }
}
static int function1_probe(void){
    uint8_t enabled,ready;
    if(read_byte(2,&enabled))return -1;
    field("SDIO IOEx before=",enabled);uart_puts("\n");
    uint8_t request=enabled|2;
    if(direct(0,2,&request,1))return -1;
    TickType_t start=xTaskGetTickCount();int result=-1;
    for(;;){
        if(read_byte(3,&ready))goto restore;
        if(ready&2)break;
        if((TickType_t)(xTaskGetTickCount()-start)>=1000){
            field("SDIO function1 not ready IORx=",ready);uart_puts("\n");goto restore;
        }
        vTaskDelay(1);
    }
    field("SDIO function1 ready IORx=",ready);uart_puts("\n");
    /* MT5931 WCIR/WHLPCR are read-only here. CMD52 byte access is probed
     * first; a result is evidence only after matching the expected chip ID. */
    for(unsigned address=0;address<8;address+=4){
        uint32_t word=0;uint8_t v;
        for(unsigned i=0;i<4;i++){
            if(direct(1,address+i,&v,0))goto restore;
            word|=(uint32_t)v<<(8*i);
        }
        field(address?"SDIO WHLPCR CMD52=":"SDIO WCIR CMD52=",word);uart_puts("\n");
        if(!address && (word&0xffff)!=0x5931){
            uart_puts("SDIO chip ID not matched; no chip writes\n");goto restore;
        }
        uint32_t raw;
        if(extended_word(address,&raw))goto restore;
        field(address?"SDIO WHLPCR CMD53 raw=":"SDIO WCIR CMD53 raw=",raw);uart_puts("\n");
        if(!address){
            uint32_t swapped=swap32(raw);
            if(raw==word)uart_puts("SDIO CMD53 WCIR matches native word\n");
            else if(swapped==word)uart_puts("SDIO CMD53 WCIR matches swapped word\n");
            else{uart_puts("SDIO CMD53/CMD52 mismatch\n");goto restore;}
            card_verified=1;
        }
    }
    result=0;
restore:
    request=enabled;
    if(direct(0,2,&request,1))return -1;
    if(read_byte(2,&request) || request!=enabled){uart_puts("SDIO IOEx restore failed\n");return -1;}
    uart_puts("SDIO IOEx restored\n");return result;
}
static int cis(unsigned function){
    uint32_t pointer=0;uint8_t v;
    for(unsigned i=0;i<3;i++){
        if(read_byte(function*0x100+9+i,&v))return -1;
        pointer|=(uint32_t)v<<(8*i);
    }
    field("SDIO CIS function=",function);field(" pointer=",pointer);uart_puts("\n");
    if(!pointer || pointer>0x1ffff)return -1;
    uint32_t start=pointer;
    for(unsigned tuples=0;tuples<128 && pointer-start<1024;tuples++){
        uint8_t code,len;
        if(read_byte(pointer++,&code))return -1;
        if(code==0xff)return 0;
        if(!code)continue;
        if(read_byte(pointer++,&len))return -1;
        if(len==0xff)return 0;
        if(pointer>0x1ffff || len>0x20000-pointer)return -1;
        if(code==0x20 && len>=4){
            uint8_t id[4];
            for(unsigned i=0;i<4;i++)if(read_byte(pointer+i,&id[i]))return -1;
            field("SDIO MANFID vendor=",id[0]|((unsigned)id[1]<<8));
            field(" device=",id[2]|((unsigned)id[3]<<8));uart_puts("\n");return 0;
        }
        pointer+=len;
    }
    uart_puts("SDIO CIS scan limit\n");return -1;
}
void sdio_identify(void){
    card_verified=0;
    wifi_hif_ready=0;
    uart_puts("SDIO identification start; no wireless transmission\n");
    host_init();status();uint32_t r;
    if(command(0x4705,0,&r))goto done;
    field("SDIO OCR probe=",r);uart_puts("\n");
    unsigned functions=(r>>28)&7;
    if(!functions || !(r&0x00100000)){uart_puts("SDIO unsupported OCR\n");goto done;}
    unsigned tries;
    for(tries=0;tries<100;tries++){
        if(command(0x4705,0x00100000,&r))goto done;
        if(r&0x80000000)break;
        vTaskDelay(10);
    }
    if(tries==100){uart_puts("SDIO card not ready\n");goto done;}
    if(command(3,0,&r))goto done;
    uint32_t rca=r&0xffff0000;
    field("SDIO RCA=",rca);uart_puts("\n");
    if(!rca || command(7,rca,&r))goto done;
    /* CMD52 uses CMD even when the powered card retained a different DAT
     * width across MCU RAM replacement. Normalize before any CMD53 reads. */
    uint8_t interface;
    if(read_byte(7,&interface))goto done;
    field("SDIO retained CCCR07=",interface);uart_puts("\n");
    if((interface&3)!=0){
        if((interface&3)!=2){uart_puts("SDIO reserved retained width\n");goto done;}
        uint8_t selected=interface&~3U,value=selected;
        if(direct(0,7,&value,1) || read_byte(7,&value) || value!=selected)goto done;
        field("SDIO normalized CCCR07=",value);field(" OPTION=",S(0x28));uart_puts("\n");
    }
    uint8_t revision;
    if(read_byte(0,&revision))goto done;
    field("SDIO CCCR revision=",revision);field(" functions=",functions);uart_puts("\n");
    if(cis(0))uart_puts("SDIO function0 CIS unavailable\n");
    if(cis(1))uart_puts("SDIO function1 CIS unavailable\n");
    if(function1_probe())uart_puts("SDIO function1 register probe incomplete\n");
done:
    S(0x24)&=(uint16_t)~0x100;
    uart_puts("SDIO identification end\n");
}
static int radio_read(unsigned address,uint32_t *value){
    uint32_t raw,begin=wifi_io.active?board_time_counts():0;
    int result=extended_word(address,&raw);
    if(wifi_io.active)wifi_io_record(&wifi_io,wifi_io_read_kind(address),4,begin,board_time_counts(),result!=0);
    if(result)return -1;
    *value=swap32(raw);return 0;
}
static int extended_write(unsigned address,const uint8_t *data,unsigned size,int increment){
    if(!size || size>4096 || (size&3) || (size>512 && (size&511)) || address>0x1ffff ||
       (increment && size>0x20000-address))return -1;
    if(bus_idle())return -1;
    unsigned blocks=size>512?size/512:0;
    S(0x26)=blocks?512:size;S(8)=blocks?0x100:0;
    if(blocks)S(0xa)=blocks;
    S(0x1c)&=(uint16_t)~4;S(0x1e)&=(uint16_t)~0x200;
    uint32_t response,arg=0x90000000UL|(address<<9)|
        (blocks?0x08000000UL|blocks:size&0x1ff);
    if(increment)arg|=0x04000000UL;
    if(command(blocks?0x6c35:0x4c35,arg,&response))return -1;
    if(response&0xcb00){field("SDIO write R5 error=",response);uart_puts("\n");return -1;}
    TickType_t start=xTaskGetTickCount();unsigned sent=0,polls=0;
    for(;;){
        unsigned info1=S(0x1c),info2=S(0x1e);
        if(info2&0x807f){uart_puts("SDIO write data error");status();return -1;}
        if(sent<size && (info2&0x200)){
            S(0x1e)&=(uint16_t)~0x200;
            unsigned end=sent+(blocks?512:size);
            for(unsigned i=sent;i<end;i+=4){
                uint32_t raw=((uint32_t)data[i]<<24)|((uint32_t)data[i+1]<<16)|
                    ((uint32_t)data[i+2]<<8)|data[i+3];
                R32(0xffffc830UL)=raw;
            }
            sent=end;
        }
        if(sent==size && (info1&4)){S(0x1c)&=(uint16_t)~4;return 0;}
        if((TickType_t)(xTaskGetTickCount()-start)>=1000){uart_puts("SDIO write data timeout");status();return -1;}
        if(transfer_wait(&polls,wifi_write_fast==2 || wifi_write_fast==3,
            sent==size?4:0,sent==size?0:0x200,start,1000))return -1;
    }
}
static int radio_write(unsigned address,uint32_t value){
    uint8_t data[4];for(unsigned i=0;i<4;i++)data[i]=(uint8_t)(value>>(8*i));
    return extended_write(address,data,4,1);
}
static int fifo_read(unsigned address,uint8_t *data,unsigned size){
    if(!size || size>4096 || (size&3) || (size>512 && (size&511)) || address>0x1ffff)return -1;
    if(bus_idle())return -1;
    unsigned blocks=size>512?size/512:0;
    S(0x26)=blocks?512:size;S(8)=blocks?0x100:0;
    if(blocks)S(0xa)=blocks;
    S(0x1c)&=(uint16_t)~4;S(0x1e)&=(uint16_t)~0x100;
    uint32_t response;
    if(command(blocks?0x7c35:0x5c35,0x10000000UL|(address<<9)|
               (blocks?0x08000000UL|blocks:size&0x1ff),&response))return -1;
    if(response&0xcb00){field("WIFI RX R5 error=",response);uart_puts("\n");return -1;}
    TickType_t start=xTaskGetTickCount();unsigned received=0,polls=0;
    for(;;){
        unsigned info1=S(0x1c),info2=S(0x1e);
        if(info2&0x807f){uart_puts("WIFI RX data error");status();return -1;}
        if(received<size && (info2&0x100)){
            S(0x1e)&=(uint16_t)~0x100;
            unsigned end=received+(blocks?512:size);
            for(unsigned i=received;i<end;i+=4){
                uint32_t raw=R32(0xffffc830UL);
                data[i]=raw>>24;data[i+1]=raw>>16;data[i+2]=raw>>8;data[i+3]=raw;
            }
            received=end;
        }
        if(received==size && (info1&4)){S(0x1c)&=(uint16_t)~4;return 0;}
        if((TickType_t)(xTaskGetTickCount()-start)>=1000){uart_puts("WIFI RX data timeout");status();return -1;}
        if(transfer_wait(&polls,0,received==size?4:0,received==size?0:0x100,
            start,1000))return -1;
    }
}
static int radio_wait(unsigned address,uint32_t mask,uint32_t reject){
    TickType_t start=xTaskGetTickCount();uint32_t value;
    for(;;){
        if(radio_read(address,&value))return -1;
        if(value&reject){field("WIFI rejected status=",value);uart_puts("\n");return -1;}
        if(value&mask)return 0;
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){
            field("WIFI wait timeout register=",address);field(" value=",value);uart_puts("\n");return -1;
        }
        vTaskDelay(10);
    }
}
static int radio_image_valid(void){
    const uint32_t *descriptor=wifi_radio_descriptor;
    const uint8_t *radio=wifi_radio_bytes;
    return descriptor[0]==0x4d543331 && descriptor[1]>0 && descriptor[1]<=262144 && !(descriptor[1]&63) &&
       descriptor[3]==0xff900000UL &&
       (uintptr_t)wifi_radio_end-(uintptr_t)radio==descriptor[1] &&
       crc32(radio,descriptor[1])==descriptor[2];
}
static int radio_boot(unsigned force){
    uart_puts("WIFI boot start\n");
    const uint8_t *radio=wifi_radio_bytes;
    const unsigned radio_length=wifi_radio_descriptor[1];
    if(!radio_image_valid()){
        uart_puts("WIFI board radio image missing or corrupt\nWIFI boot end status=failed\n");return -1;
    }
    /* Whole-chip reset preserves HIFSYS and the selected SDIO function.
     * Reissuing CMD5/CMD3/CMD7 here is outside the reference reload sequence. */
    if(!force)sdio_identify();
    if(!card_verified){uart_puts("WIFI chip not verified\nWIFI boot end status=failed\n");return -1;}
    S(0x24)|=0x100;uint8_t enable=2;
    int result=-1;unsigned download_mode=0;uint32_t value;
    if(!force && direct(0,2,&enable,1))goto done;
    TickType_t start=xTaskGetTickCount();
    for(;;){
        uint8_t ready;if(read_byte(3,&ready))goto done;
        if(ready&2)break;
        if((TickType_t)(xTaskGetTickCount()-start)>=1000)goto done;
        vTaskDelay(1);
    }
    if(radio_read(0,&value) || (value&0xffff)!=0x5931)goto done;
    if((value&0x200000) && !force){uart_puts("WIFI firmware already ready; no reload\n");result=0;goto done;}
    if(radio_read(0x8c,&value))goto done;
    field("WIFI WMCSR before=",value);uart_puts("\n");
    /* No guessed GPIO or whole-chip reset. Existing INI_RDY must be present. */
    if(radio_wait(0x8c,0x800,0))goto done;
    if(radio_write(0x90,radio_length>>6) || radio_write(0x8c,1))goto done;
    if(radio_wait(0x8c,0x2000,0x4000))goto done;
    uart_puts("WIFI PLL ready\n");
    download_mode=1;
    if(radio_write(0x88,1) || radio_write(0x84,0xff900000UL))goto done;
    static uint8_t packet[512];
    for(unsigned offset=0;offset<radio_length;){
        unsigned n=radio_length-offset;if(n>508)n=508;
        unsigned length=(n+7)&~3U;
        packet[0]=(uint8_t)length;packet[1]=(uint8_t)(length>>8);packet[2]=packet[3]=0;
        for(unsigned i=0;i<n;i++)packet[i+4]=radio[offset+i];
        for(unsigned i=n+4;i<length;i++)packet[i]=0;
        if(radio_wait(0x88,0x100,0) || extended_write(0x80,packet,length,0))goto done;
        offset+=n;
        if(!(offset&0x3fff) || offset==radio_length){field("WIFI downloaded=",offset);uart_puts("\n");}
    }
    if(radio_wait(0x8c,0x8000,0x4000))goto done;
    uart_puts("WIFI download OK\n");
    if(radio_write(0x88,0))goto done;
    download_mode=0;
    if(radio_wait(0,0x200000,0))goto done;
    if(radio_read(0,&value))goto done;
    field("WIFI WCIR ready=",value);uart_puts("\n");
    if(radio_write(4,0x200) || radio_wait(4,0x100,0))goto done;
    if(radio_read(4,&value))goto done;
    field("WIFI driver own=",value);uart_puts("\n");
    wifi_scan_unresolved=0; /* Reached only after complete firmware download. */
    wifi_connection_unresolved=0;
    result=0;
done:
    if(result && download_mode)radio_write(0x88,0);
    /* Success leaves function1 and clock active for the forthcoming driver.
     * Failure is bounded and returns to the UART/RTOS application. */
    if(result)S(0x24)&=(uint16_t)~0x100;
    uart_puts(result?"WIFI boot end status=failed\n":"WIFI boot end status=ready\n");
    return result;
}
void sdio_wifi_boot(void){(void)radio_boot(0);}
void sdio_wifi_restart(void){
    uart_puts("WIFI restart start\n");
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending ||
       wifi_management_pending || wifi_data_count || wifi_scan_active ||
       wifi_bench_active || wifi_sink_active || wifi_feedback.pending ||
       tuner_ts_stream_active()){
        uart_puts("WIFI restart end status=refused-active\n");return;
    }
    if(!card_verified || !(S(0x24)&0x100) || !radio_image_valid()){
        uart_puts("WIFI restart end status=refused-state\n");return;
    }
    wifi_scan_cache_finish(&wifi_bss_cache,0);
    uint32_t chip,control;unsigned stage=1;
    if(radio_read(0,&chip) || (chip&0xffff)!=0x5931 ||
       radio_write(4,0x200) || radio_wait(4,0x100,0))goto failed;
    field("WIFI reset before WCIR=",chip);uart_puts("\n");
    stage=2;
    /* MT5931 reference uses WMCSR.CHIP_RST (write bit15), then zero,
     * with 120ms before checking INI_RDY. HIFSYS is preserved. No GPIO. */
    if(sdio_irq_set(0))goto failed;
    wifi_hif_ready=0;wifi_tx_fault=1; /* No stale credit can be reused. */
    stage=3;
    if(radio_write(0x8c,0x8000) || radio_write(0x8c,0))goto failed;
    vTaskDelay(120);
    stage=4;
    if(radio_wait(0x8c,0x800,0) || radio_read(0,&chip) ||
       (chip&0xffff)!=0x5931)goto failed;
    /* HIFSYS is retained by this reset. WCIR.WLAN_READY alone cannot prove
     * a fresh session; force the complete download and verify its result. */
    field("WIFI reset INI_RDY WCIR=",chip);uart_puts("\n");
    wifi_mac_valid=wifi_board_sent=0;
    wifi_dpd_attempted=wifi_dpd_transferred=0;
    wifi_osc_attempted=0;
    wifi_per_attempted=wifi_per_transferred=wifi_per_steps=0;
    wifi_sequence=0;wifi_channel_token=1;
    wifi_tc1_free=wifi_tc2_free=wifi_tc3_free=wifi_tc4_free=wifi_tc5_free=0;
    wifi_credit_fresh=wifi_credit_probe=wifi_status_polling=wifi_poll_reuse=0;
    wifi_status_rx=0;wifi_management_length=0;
    wifi_peer_active=wifi_peer_activated=0;
    wifi_ap_stop_ok=0;
    wifi_peer_ht=(struct wifi_ht_peer){0};
    wifi_power_events_reset(&wifi_power);
    stage=5;
    if(radio_boot(1))goto failed;
    stage=6;
    if(!card_verified || radio_read(0,&chip) || (chip&0x20ffff)!=0x205931 ||
       radio_read(4,&control) || !(control&0x100))goto failed;
    wifi_tx_fault=0;wifi_scan_unresolved=0;
    wifi_connection_unresolved=0;
    uart_puts("WIFI restart end status=ready\n");return;
failed:
    /* A write may have partially reached the chip. Do not retry or report
     * a new session ready without reset and firmware readiness evidence. */
    wifi_hif_ready=0;wifi_tx_fault=1;wifi_scan_unresolved=1;
    field("WIFI restart failed stage=",stage);uart_puts("\n");
    uart_puts("WIFI restart end status=failed\n");
}
void sdio_wifi_mac(void){
    wifi_mac_valid=0;
    uart_puts("WIFI MAC query start\n");
    int result=-1;
    uint8_t command_packet[20]={0};
    /* One TC4 query to TX1; not an RF-test or connection command. */
    if(control_send(0xc1,0,command_packet,sizeof command_packet))goto done;
    uint8_t sequence=wifi_sequence;
    uart_puts("WIFI MAC command sent\n");
    TickType_t start=xTaskGetTickCount();unsigned events=0;
    static uint8_t packet[4096];
    for(;;){
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)goto done;
        if(got){
            if(++events>16)goto done;
            if(packet[4]==9 && packet[5]==sequence){
                if(length!=20){uart_puts("WIFI invalid basic configuration length\n");goto done;}
                unsigned any=0,all=0xff;
                for(unsigned i=8;i<14;i++){any|=packet[i];all&=packet[i];}
                if(!any || all==0xff || (packet[8]&1)){uart_puts("WIFI invalid MAC\n");goto done;}
                uart_puts("WIFI MAC=");
                for(unsigned i=0;i<6;i++)wifi_mac[i]=packet[i+8];
                wifi_mac_valid=1;
                const char *hex="0123456789abcdef";
                for(unsigned i=8;i<14;i++){
                    char byte[4]={hex[packet[i]>>4],hex[packet[i]&15],i==13?'\n':':',0};
                    uart_puts(byte);
                }
                result=0;goto done;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){
            uart_puts("WIFI MAC response timeout\n");goto done;
        }
        vTaskDelay(1);
    }
done:
    uart_puts(result?"WIFI MAC query end status=failed\n":"WIFI MAC query end status=ready\n");
}
static int tx_poll(void){
    uint32_t status_value,other=0,value=0;
    wifi_credit_fresh=0;++wifi_poll_count;
    if(wifi_status_polling){
        uint8_t bytes[88];struct wifi_status snapshot;
        wifi_status_rx=0;++wifi_status_reads;
        uint32_t io_begin=wifi_io.active?board_time_counts():0;
        int io_result=fifo_read(0x10,bytes,sizeof bytes);
        if(wifi_io.active)wifi_io_record(&wifi_io,WIFI_IO_SNAPSHOT,sizeof bytes,io_begin,board_time_counts(),io_result!=0);
        if(io_result){
            uart_puts("WIFI status snapshot read-failed\n");
            wifi_tx_fault=1;return -1;
        }
        if(!wifi_status_decode(bytes,sizeof bytes,&snapshot)){
            uart_puts("WIFI status snapshot invalid\n");
            for(unsigned n=0;n<sizeof bytes;n+=4){
                field("WIFI status raw offset=",n);
                field(" bytes=",((uint32_t)bytes[n]<<24)|((uint32_t)bytes[n+1]<<16)|
                    ((uint32_t)bytes[n+2]<<8)|bytes[n+3]);uart_puts("\n");
            }
            wifi_tx_fault=1;return -1;
        }
        status_value=snapshot.interrupt;other=snapshot.tx0;value=snapshot.tx1;
        wifi_status_rx=snapshot.rx_lengths;
    }else if(radio_read(0x10,&status_value))return -1;
    if(status_value&8){
        uint32_t abnormal;
        if(!radio_read(0x18,&abnormal)){field("WIFI abnormal WASR=",abnormal);uart_puts("\n");}
        wifi_tx_fault=1;return -1;
    }
    if(wifi_timing_enabled)wifi_tx_timing_poll(&wifi_timing,xTaskGetTickCount());
    /* Optional diagnostic: Linux resource polling reads WTSR without a
     * TX_DONE prerequisite. Probe only when tracked buffers are outstanding;
     * consume each read-clear result through this same bounded accounting path. */
    unsigned extra=wifi_credit_probe && !wifi_status_polling && !(status_value&1) &&
        (wifi_tc1_free<14 || wifi_tc2_free<1 || wifi_tc3_free<1 ||
         wifi_tc4_free<4 || wifi_tc5_free<1);
    if((status_value&1) || extra){
        if(!wifi_status_polling && (radio_read(0x20,&other) || radio_read(0x24,&value))){
            /* A first read may already have cleared counters. Never retry
             * uncertain accounting or grant the remaining partial result. */
            wifi_tx_fault=1;return -1;
        }
        if(extra)++wifi_probe_reads;
        if(wifi_verbose || (value&0xff)){
            field("WIFI TX released WTSR0=",other);field(" WTSR1=",value);uart_puts("\n");
        }
        if(wifi_hif_ready){
            unsigned released=value&0xff;
            if(released>4-wifi_tc4_free){uart_puts("WIFI TC4 credit overflow\n");wifi_tx_fault=1;return -1;}
            wifi_tc4_free+=released;
            unsigned video_released=(other>>16)&0xff,voice_released=(other>>24)&0xff;
            if(wifi_tc2_free>1 || wifi_tc3_free>1 || video_released>1-wifi_tc2_free || voice_released>1-wifi_tc3_free){
                uart_puts("WIFI QoS credit overflow\n");wifi_tx_fault=1;return -1;
            }
            unsigned data_released=(other>>8)&0xff,group_released=(value>>8)&0xff;
            if(data_released>14-wifi_tc1_free || group_released>1-wifi_tc5_free){
                uart_puts("WIFI data credit overflow\n");wifi_tx_fault=1;return -1;
            }
            if(extra)wifi_probe_released+=released+video_released+voice_released+data_released+group_released;
            wifi_tc1_free+=data_released;wifi_tc5_free+=group_released;
            wifi_tc2_free+=video_released;wifi_tc3_free+=voice_released;
            bench_credit_returned(data_released);
            if(wifi_timing_enabled && data_released)
                wifi_tx_timing_credit(&wifi_timing,wifi_tc1_free,xTaskGetTickCount());
        }
    }
    if(wifi_tx_fault)return -1;
    wifi_credit_fresh=1;return 0;
}
static int data_credit(unsigned available){
    if(wifi_tx_fault)return -1;
    /* A successful poll in this loop already accounted for read-clear
     * release counters. Reusing a positive balance cannot grant new credit. */
    if(wifi_poll_reuse && wifi_credit_fresh && available){
        ++wifi_reuse_count;return 0;
    }
    return tx_poll();
}
/* Single SDIO owner only. Waiting must precede publishing management TX state.
 * Commands, management and future AIS security frames share the same TC4 pool. */
static int tc4_wait(void){
    if(!wifi_hif_ready || wifi_tx_fault)return -1;
    TickType_t start=xTaskGetTickCount();
    for(;;){
        if(tx_poll())return -1;
        if(wifi_tc4_free>4){wifi_tx_fault=1;return -1;}
        if(wifi_tc4_free)return 0;
        if((TickType_t)(xTaskGetTickCount()-start)>=1000){uart_puts("WIFI TC4 credit timeout\n");return -1;}
        vTaskDelay(1);
    }
}
static int tc4_write(const uint8_t *packet,unsigned length){
    /* Never rewrite a caller's HIF header: security frames are not commands.
     * A returned credit means buffer release, not firmware/over-air success. */
    if(!wifi_hif_ready || wifi_tx_fault || wifi_connection_unresolved || !packet || length<8 ||
       length>4096 || (length&3) || (length>512 && (length&511)))return -1;
    unsigned logical=packet[0]|((unsigned)packet[1]<<8);
    if(logical<8 || logical>length)return -1;
    if(wifi_tc4_free>4){wifi_tx_fault=1;return -1;}
    if(!wifi_tc4_free)return -1;
    --wifi_tc4_free;
    /* A failed SDIO transaction may already have reached the radio. Do not
     * refund or retry; recovery must reestablish the radio's buffer state. */
    if(extended_write(0x2c,packet,length,0)){wifi_tx_fault=1;return -1;}
    return 0;
}
int sdio_wifi_wpa_eapol_submit(unsigned port,unsigned tc,const unsigned char *p,unsigned n){
    if(port!=0x2c || tc!=4 || !p || n<36 || n>2560 ||
       !wifi_hif_ready || !wifi_mac_valid || wifi_tx_fault || wifi_connection_unresolved ||
       wifi_ap_active || wifi_peer_state || !wifi_ais_connection.watch ||
       !wifi_ais_connection.activated || !wifi_ais_connection.beacon_seen ||
       !wifi_ais_connection.aid || p[2]!=14 || p[3]!=16 || p[4]!=14 ||
       p[5]!=0x40 || p[6] || p[7] || p[8] || p[9] || p[10] ||
       p[11]!=0x20 || p[12] || p[13] || p[14] || p[15])return -1;
    unsigned logical=p[0]|((unsigned)p[1]<<8),padded=(logical+3)&~3U;
    if(padded>512)padded=(padded+511)&~511U;
    if(logical<34 || logical>2078 || padded!=n || p[28]!=0x88 || p[29]!=0x8e ||
       (p[30]!=1 && p[30]!=2) || p[31]!=3 ||
       ((unsigned)p[32]<<8|p[33])!=logical-34)return -1;
    for(unsigned i=0;i<6;i++)if(p[16+i]!=wifi_ais_connection.selected.ap[i] ||
        p[22+i]!=wifi_mac[i])return -1;
    for(unsigned i=logical;i<n;i++)if(p[i])return -1;
    if(tc4_wait())return -1;
    return tc4_write(p,n);
}
static int control_send(unsigned cid,unsigned set,uint8_t *packet,unsigned length){
    uint32_t value;
    if(wifi_ais_retained_active && set && cid!=8 && !wifi_ais_retained_teardown){
        uart_puts("WIFI command refused: retained AIS owner active\n");return -1;
    }
    if(wifi_connection_unresolved){
        uart_puts("WIFI command refused: unresolved AIS cleanup; cold radio restart required\n");
        return -1;
    }
    if(length<8 || length>512 || (length&3))return -1;
    if(!(S(0x24)&0x100) || radio_read(0,&value) ||
       (value&0x20ffff)!=0x205931){uart_puts("WIFI run boot first\n");return -1;}
    if(radio_write(4,0x200) || radio_wait(4,0x100,0))return -1;
    /* Normal HIF setup: one reported RX length, no RX enhancement, read-clear
     * status. Device interrupt sources enabled; SoC interrupts stay masked. */
    if(!wifi_hif_ready){
        wifi_tx_fault=0;
        uint8_t capability,low=0,high=2;
        if(read_byte(8,&capability) || !(capability&2)){
            uart_puts("WIFI card block mode unsupported\n");return -1;
        }
        if(direct(0,0x110,&low,1) || direct(0,0x111,&high,1) ||
           read_byte(0x110,&low) || read_byte(0x111,&high) || low || high!=2)return -1;
        uart_puts("WIFI function1 block size=512\n");
        if(radio_read(0x0c,&value))return -1;
        field("WIFI WHCR before=",value);uart_puts("\n");
        if(radio_write(0x0c,(value&~0x100f2UL)|0x10) ||
           radio_write(0x14,0xffffff0fUL) || radio_write(4,1))return -1;
        /* RAM application replacement does not reset the radio. Drain old
         * responses before reusing sequence numbers in the new application. */
        uart_puts("WIFI drain old RX start\n");
        static uint8_t old_packet[4096];unsigned count;
        for(count=0;count<128;count++){
            unsigned old_length;
            if(event_read(old_packet,sizeof old_packet,&old_length)<0)return -1;
            if(!old_length)break;
        }
        if(count==128){uart_puts("WIFI old RX drain limit\n");return -1;}
        field("WIFI drain old RX count=",count);uart_puts("\n");
        /* MT5931 normal-mode TC4 has four buffers in the chip-specific public
         * driver. Discard old-session counters before seeding a fresh pool. */
        if(radio_read(0x20,&value) || radio_read(0x24,&value))return -1;
        wifi_tc4_free=4;
        wifi_tc1_free=14;wifi_tc2_free=wifi_tc3_free=wifi_tc5_free=1;
        wifi_hif_ready=1;
    }
    if(tc4_wait())return -1;
    if(!++wifi_sequence)++wifi_sequence;
    packet[0]=length;packet[1]=length>>8;packet[2]=0;packet[3]=0x50;
    packet[4]=cid;packet[5]=set;packet[6]=wifi_sequence;packet[7]=0;
    if(tc4_write(packet,length))return -1;
    field("WIFI TC4 reserved remaining=",wifi_tc4_free);uart_puts("\n");
    /* Read matching firmware response before considering the query complete.
     * Resource notifications are polled independently by event_read. */
    return 0;
}
static void beacon_read(const uint8_t *packet,unsigned length){
    if(length<12 || !(packet[5]&1))return;
    unsigned offset=12+(packet[4]&3);
    if(length<offset+36 || (packet[offset]&0xfc)!=0x80 || packet[offset+1])return;
    unsigned ssid_offset=0,ssid_length=0,channel=packet[10];
    for(unsigned pos=offset+36;pos<length;){
        if(length-pos<2 || packet[pos+1]>length-pos-2)return;
        unsigned n=packet[pos+1];
        if(!packet[pos] && n<=32){ssid_offset=pos+2;ssid_length=n;}
        if(packet[pos]==3 && n==1)channel=packet[pos+2];
        pos+=2+n;
    }
    if(!ssid_offset)return;
    ++wifi_beacons;
    field("WIFI beacon channel=",channel);field(" RCPI=",packet[9]);uart_puts(" BSSID=");
    const char *hex="0123456789abcdef";
    for(unsigned i=offset+16;i<offset+22;i++){
        char byte[3]={hex[packet[i]>>4],hex[packet[i]&15],0};uart_puts(byte);
    }
    uart_puts(" SSID_hex=");
    for(unsigned i=ssid_offset;i<ssid_offset+ssid_length;i++){
        char byte[3]={hex[packet[i]>>4],hex[packet[i]&15],0};uart_puts(byte);
    }
    uart_puts("\n");
    /* Copy negotiated inputs out of the reusable FIFO buffer. Discovery only:
     * no BSS/PM updates or automatic connection to an observed network. */
    static struct wifi_ais_beacon parsed;
    if(wifi_scan_active && wifi_ais_beacon_parse(packet+offset,length-offset,packet[10],0,wifi_rate_profile,&parsed)){
        wifi_scan_cache_observe(&wifi_bss_cache,&parsed,xTaskGetTickCount(),wifi_rate_profile,packet[9]);
        field("WIFI beacon params capability=",parsed.capability);
        field(" interval=",parsed.interval);field(" operational=",parsed.operational);
        field(" basic=",parsed.basic);field(" DS_channel=",parsed.channel);
        field(" RX_channel=",parsed.rx_channel);field(" TIM=",parsed.tim_present);
        field(" DTIM_count=",parsed.dtim_count);field(" DTIM_period=",parsed.dtim_period);
        field(" ERP_protection=",parsed.erp_protection);field(" short_preamble=",parsed.short_preamble);
        field(" short_slot=",parsed.short_slot);field(" RSN_bytes=",parsed.rsn_length);
        uart_puts("\n");
    }
}
static int event_read(uint8_t *packet,unsigned capacity,unsigned *length){
    uint32_t value;
    if(tx_poll())return -1;
    if(wifi_status_polling)value=wifi_status_rx;
    else if(radio_read(0x50,&value))return -1;
    *length=value>>16;
    unsigned port=1;
    if(!*length){*length=value&0xffff;port=0;}
    if(!*length)return 0;
    unsigned read_length=((*length+3)&~3U)+(port?0:4);
    if(read_length>512)read_length=(read_length+511)&~511U;
    if(*length<8 || read_length>capacity){field("WIFI RX unsupported length=",*length);uart_puts("\n");return -1;}
    uint32_t io_begin=wifi_io.active?board_time_counts():0;
    int io_result=fifo_read(port?0x34:0x30,packet,read_length);
    if(wifi_io.active)wifi_io_record(&wifi_io,WIFI_IO_RX_FIFO,read_length,io_begin,board_time_counts(),io_result!=0);
    if(io_result)return -1;
    unsigned stated=packet[0]|((unsigned)packet[1]<<8);
    unsigned type=packet[2]|((unsigned)packet[3]<<8);
    if(stated!=*length)return -1;
    wifi_wpa_radio_rx(packet,stated);
    wifi_ais_join_observe(&wifi_ais_connection,packet,stated);
    if((type&3)!=1){
        if((type&3) || wifi_verbose){
            field("WIFI RX port=",port);field(" length=",stated);field(" type=",type);uart_puts("\n");
        }
        if(!(type&3) && wifi_ap_active){
            struct wifi_ethernet_view view;
            if(wifi_hif_ethernet(packet,*length,1,&view)){
                unsigned from_peer=1;
                for(unsigned i=0;i<6;i++)if(view.frame[6+i]!=wifi_peer[i])from_peer=0;
                if(wifi_peer_activated && !view.station && from_peer &&
                   (view.ethertype==0x0800 || view.ethertype==0x0806)){
                    ++wifi_data_rx;
                    if(wifi_sink_active && wifi_rx_sink_receive(&wifi_sink,view.frame,view.length,wifi_mac,wifi_peer,xTaskGetTickCount())){
                        /* RX-only diagnostic: consume before the reply queue. */
                    }else if(wifi_data_count<4){
                        unsigned slot=(wifi_data_head+wifi_data_count)&3;
                        for(unsigned i=0;i<view.length;i++)wifi_data[slot][i]=view.frame[i];
                        wifi_data_lengths[slot]=view.length;++wifi_data_count;
                    }else ++wifi_data_dropped;
                }
                if(wifi_verbose){
                field("WIFI data format=",packet[5]);field(" offset=",packet[4]&3);
                field(" Ethernet_length=",view.length);field(" EtherType=",view.ethertype);
                field(" station=",view.station);field(" RCPI=",view.rcpi);
                uart_puts(" source=");
                for(unsigned i=6;i<12;i++){uart_hex(view.frame[i]);uart_puts(" ");}
                if(view.ethertype==0x0800 && view.length>=34 && view.frame[14]==0x45){
                    field(" IP_protocol=",view.frame[23]);
                    if(view.frame[23]==17 && view.length>=42){
                        field(" UDP_source=",((unsigned)view.frame[34]<<8)|view.frame[35]);
                        field(" UDP_dest=",((unsigned)view.frame[36]<<8)|view.frame[37]);
                    }
                }
                uart_puts("\n");
                }
            }else if(wifi_verbose)uart_puts("WIFI Ethernet_view=unsupported\n");
        }
        if((type&3)==3){
            beacon_read(packet,*length);
            unsigned offset=12+(packet[4]&3);
            if(wifi_ap_active && *length>=offset+24 && (packet[5]&1) &&
               (packet[offset]==0x40 || packet[offset]==0xb0 || packet[offset]==0) &&
               *length-offset<=sizeof wifi_management && !wifi_management_length){
                field("WIFI management RX subtype=",packet[offset]);uart_puts("\n");
                wifi_management_length=*length-offset;
                wifi_management_rcpi=packet[9];
                for(unsigned i=0;i<wifi_management_length;i++)wifi_management[i]=packet[offset+i];
            }
        }
        return 0;
    }
    if(wifi_ap_active && packet[4]==0x17 && stated>=12 && (packet[8]&128U)){
        uint32_t sequence;
        if(wifi_tx_feedback_complete(&wifi_feedback,packet[8],packet[9],&sequence)){
            if(wifi_timing_enabled)wifi_tx_timing_done(&wifi_timing,packet[8],packet[9],xTaskGetTickCount());
            if(packet[9] && wifi_verbose){
                field("WIFI sampled TS TX done sequence=",sequence);
                field(" status=",packet[9]);uart_puts("\n");
            }
        }
        return 1;
    }
    /* Power observations never grant HIF credits or alter TX scheduling. */
    if(wifi_ap_active && (packet[4]==0x19 || packet[4]==0x1a || packet[4]==0x1e))
        wifi_power_events_observe(&wifi_power,packet,stated,1,0);
    field("WIFI event length=",stated);field(" type=",type);
    field(" id=",packet[4]);field(" sequence=",packet[5]);uart_puts("\n");
    if(packet[4]==0x18 && stated>=20){
        field("WIFI channel event network=",packet[8]);field(" token=",packet[9]);
        field(" status=",packet[10]);field(" channel=",packet[11]);
        field(" sco=",packet[12]);field(" band=",packet[13]);
        field(" request=",packet[14]);
        uint32_t interval=packet[16]|((uint32_t)packet[17]<<8)|
            ((uint32_t)packet[18]<<16)|((uint32_t)packet[19]<<24);
        field(" interval_ms=",interval);uart_puts("\n");
    }
    if(wifi_ap_active && packet[4]==0x17 && stated>=12){
        field("WIFI management TX done sequence=",packet[8]);
        field(" status=",packet[9]);uart_puts("\n");
        if(wifi_management_pending && packet[8]==wifi_management_pending_sequence){
            wifi_management_done=1;wifi_management_result=packet[9];
        }
    }
    if(wifi_ap_active && packet[4]==0x13){
        uart_puts("WIFI station activation body=");
        for(unsigned i=8;i<stated && i<24;i++){uart_hex(packet[i]);uart_puts(" ");}
        uart_puts("\n");
        if(wifi_peer_activate_pending && stated>=16 && !packet[14] && packet[15]==1){
            unsigned same=1;for(unsigned i=0;i<6;i++)if(packet[8+i]!=wifi_peer[i])same=0;
            if(same){wifi_peer_activated=1;wifi_peer_activate_pending=0;}
        }
    }
    return 1;
}
void sdio_wifi_link(void){
    uart_puts("WIFI link quality start\n");
    uint8_t query[8]={0};static uint8_t packet[4096];struct wifi_link_quality quality;
    int result=-1;
    if(control_send(0x81,0,query,sizeof query))goto done;
    uint8_t sequence=wifi_sequence;TickType_t start=xTaskGetTickCount();
    for(;;){
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)goto done;
        if(got && packet[5]==sequence){
            if(packet[4]==5){
                uart_puts("WIFI link raw body=");
                for(unsigned n=8;n<length;n++){uart_hex(packet[n]);uart_puts(" ");}
                uart_puts("\n");
                if(!wifi_link_decode(packet,length,sequence,&quality)){
                    uart_puts("WIFI link unsupported response\n");goto done;
                }
                for(unsigned n=0;n<quality.count;n++){
                    struct wifi_link_entry *entry=quality.entry+n;
                    field("WIFI link network=",n);field(" rssi_signed=",(uint32_t)entry->rssi);
                    field(" quality_raw=",entry->quality_raw);field(" speed_raw=",entry->speed_raw);
                    field(" busy_raw=",entry->busy_raw);field(" ready_known=",quality.ready_known);
                    field(" ready=",entry->ready);uart_puts("\n");
                }
                result=0;goto done;
            }
            if(packet[4]==1 && length>=12 && packet[8]==0x81 && packet[9]){
                field("WIFI link rejected status=",packet[9]);uart_puts("\n");goto done;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){uart_puts("WIFI link timeout\n");goto done;}
        vTaskDelay(1);
    }
done:
    uart_puts(result?"WIFI link quality end status=failed\n":"WIFI link quality end status=read\n");
}
static int radio_debug_read(unsigned group){
    const char *status="failed";
    int result=0;
    uint8_t query[272];static uint8_t packet[4096];uint32_t words[64];
    uart_puts("WIFI radio debug start\n");
    field("WIFI radio debug group=",group);uart_puts("\n");
    if(tuner_ts_stream_active()){status="refused-stream";goto done;}
    if(!wifi_hif_ready || wifi_tx_fault){status="refused-state";goto done;}
    if(!wifi_radio_debug_group_query(query,sizeof query,group) || control_send(0xc6,0,query,sizeof query))goto done;
    uint8_t sequence=wifi_sequence;TickType_t start=xTaskGetTickCount();
    for(;;){
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)goto done;
        if(got && packet[5]==sequence){
            if(packet[4]==0x1f){
                field("WIFI radio debug raw_length=",length);uart_puts("\n");
                if(length>=16){
                    uart_puts("WIFI radio debug response_prefix=");
                    const char *hex="0123456789abcdef";
                    for(unsigned n=0;n<16;n++){
                        char byte[3]={hex[packet[n]>>4],hex[packet[n]&15],0};uart_puts(byte);
                    }
                    uart_puts("\n");
                }
                if(!wifi_radio_debug_group_decode(packet,length,sequence,group,words)){
                    status="unsupported-layout";goto done;
                }
                for(unsigned n=0;n<64;n++){
                    field("WIFI radio debug raw_index=",n);field(" value=",words[n]);uart_puts("\n");
                }
                result=1;status="read-raw";goto done;
            }
            if(packet[4]==1 && length>=12 && packet[8]==0xc6 && packet[9]){
                field("WIFI radio debug rejected status=",packet[9]);uart_puts("\n");
                status="rejected";goto done;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){status="timeout";goto done;}
        vTaskDelay(1);
    }
done:
    uart_puts("WIFI radio debug end status=");uart_puts(status);uart_puts("\n");
    return result;
}
static int rate_mailbox_read(unsigned index){
    uint8_t query[16];static uint8_t packet[4096];uint32_t raw;
    if(!wifi_rate_mailbox_query(query,sizeof query,index) ||
       control_send(0xc2,0,query,sizeof query))return -1;
    uint8_t sequence=wifi_sequence;TickType_t start=xTaskGetTickCount();
    for(;;){
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)return -1;
        if(got && packet[5]==sequence){
            if(packet[4]==0x0a){
                uart_puts("WIFI rate mailbox response_prefix=");
                const char *hex="0123456789abcdef";
                for(unsigned n=0;n<length && n<16;n++){
                    char byte[3]={hex[packet[n]>>4],hex[packet[n]&15],0};uart_puts(byte);
                }
                uart_puts("\n");
                if(!wifi_rate_mailbox_decode(packet,length,sequence,index,&raw)){
                    field("WIFI rate mailbox unsupported length=",length);uart_puts("\n");return -1;
                }
                field("WIFI rate mailbox address=",0x90000100UL+index*4);
                field(" raw=",raw);uart_puts("\n");return 0;
            }
            if(packet[4]==1 && length>=12 && packet[8]==0xc2 && packet[9]){
                field("WIFI rate mailbox rejected status=",packet[9]);uart_puts("\n");return -1;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){
            uart_puts("WIFI rate mailbox timeout\n");return -1;
        }
        vTaskDelay(1);
    }
}
void sdio_wifi_rate_mailbox(void){
    if(!wifi_hif_ready || wifi_tx_fault || wifi_management_pending ||
       wifi_peer_activate_pending || tuner_ts_stream_active()){
        uart_puts("WIFI rate mailbox end status=refused-state\n");return;
    }
    uart_puts("WIFI rate mailbox start; raw values are not PHY rates\n");
    for(unsigned n=0;n<2;n++)if(rate_mailbox_read(n)){
        uart_puts("WIFI rate mailbox end status=failed\n");return;
    }
    uart_puts("WIFI rate mailbox end status=read-raw\n");
}
void sdio_wifi_radio_debug(void){(void)radio_debug_read(0);}
void sdio_wifi_radio_groups(void){
    uart_puts("WIFI radio groups start\n");
    for(unsigned group=1;group<=3;group++){
        if(!radio_debug_read(group)){
            uart_puts("WIFI radio groups end status=failed\n");return;
        }
    }
    uart_puts("WIFI radio groups end status=read-raw\n");
}
void sdio_wifi_station_stats(void){
    uart_puts("WIFI station stats start\n");
    const char *status="failed";
    uint8_t query[272];static uint8_t packet[4096];uint32_t flags;
    if(!wifi_ap_active || !wifi_peer_active){status="refused-peer";goto done;}
    if(!wifi_compile_query(query,sizeof query,0) || control_send(0xc6,0,query,sizeof query))goto done;
    uint8_t sequence=wifi_sequence;TickType_t start=xTaskGetTickCount();
    for(;;){
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)goto done;
        if(got && packet[5]==sequence){
            if(packet[4]==0x1f){
                if(!wifi_compile_decode(packet,length,sequence,0,&flags)){status="malformed";goto done;}
                field("WIFI station stats compile_flags0=",flags);uart_puts("\n");
                if(!(flags&1)){status="unsupported";goto done;}
                break;
            }
            if(packet[4]==1 && length>=12 && packet[8]==0xc6 && packet[9]){
                field("WIFI station stats compile query rejected status=",packet[9]);uart_puts("\n");
                status="rejected";goto done;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){status="timeout-compile";goto done;}
        vTaskDelay(1);
    }
    if(!wifi_station_query(query,sizeof query,wifi_peer) || control_send(0x85,0,query,36))goto done;
    sequence=wifi_sequence;start=xTaskGetTickCount();
    for(;;){
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)goto done;
        if(got && packet[5]==sequence){
            if(packet[4]==0x29){
                field("WIFI station stats raw_length=",length);uart_puts("\n");
                if(length>128){status="unsupported-layout";goto done;}
                const char *hex="0123456789abcdef";
                uart_puts("WIFI station stats raw_body=");
                for(unsigned n=8;n<length;n++){
                    char byte[3]={hex[packet[n]>>4],hex[packet[n]&15],0};uart_puts(byte);
                }
                uart_puts("\n");status="read-raw";goto done;
            }
            if(packet[4]==1 && length>=12 && packet[8]==0x85 && packet[9]){
                field("WIFI station stats rejected status=",packet[9]);uart_puts("\n");
                status="rejected";goto done;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){status="timeout-station";goto done;}
        vTaskDelay(1);
    }
done:
    uart_puts("WIFI station stats end status=");uart_puts(status);uart_puts("\n");
}
void sdio_wifi_nic_stats(void){
    static const char *const names[12]={"transmitted_fragment","multicast_transmitted",
        "failed","retry","multiple_retry","rts_success","rts_failure","ack_failure",
        "frame_duplicate","received_fragment","multicast_received","fcs_error"};
    uart_puts("WIFI NIC statistics start\n");
    uint8_t query[8]={0};static uint8_t packet[4096];struct wifi_counter counters[12];
    int result=-1;
    if(control_send(0x82,0,query,sizeof query))goto done;
    uint8_t sequence=wifi_sequence;TickType_t start=xTaskGetTickCount();
    for(;;){
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)goto done;
        if(got && packet[5]==sequence){
            if(packet[4]==6){
                if(!wifi_statistics_decode(packet,length,sequence,counters)){
                    uart_puts("WIFI NIC statistics malformed\n");goto done;
                }
                for(unsigned n=0;n<12;n++){
                    uart_puts("WIFI NIC counter ");uart_puts(names[n]);
                    field(" high=",counters[n].high);field(" low=",counters[n].low);uart_puts("\n");
                }
                result=0;goto done;
            }
            if(packet[4]==1 && length>=12 && packet[8]==0x82 && packet[9]){
                field("WIFI NIC statistics rejected status=",packet[9]);uart_puts("\n");goto done;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){
            uart_puts("WIFI NIC statistics timeout\n");goto done;
        }
        vTaskDelay(1);
    }
done:
    uart_puts(result?"WIFI NIC statistics end status=failed\n":"WIFI NIC statistics end status=ready\n");
}
void sdio_wifi_capability(void){
    uart_puts("WIFI capability start\n");
    uint8_t command_packet[28]={0};static uint8_t packet[4096];int result=-1;
    if(control_send(0x80,0,command_packet,sizeof command_packet))goto done;
    TickType_t start=xTaskGetTickCount();unsigned events=0;
    for(;;){
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)goto done;
        if(got){
            if(++events>16)goto done;
            if(packet[4]==2 && packet[5]==wifi_sequence){
                if(length<20)goto done;
                field("WIFI product=",packet[8]|((unsigned)packet[9]<<8));
                field(" firmware=",packet[10]|((unsigned)packet[11]<<8));
                field(" driver=",packet[12]|((unsigned)packet[13]<<8));uart_puts("\n");
                field("WIFI 5GHz_disabled=",packet[14]);field(" EEPROM_used=",packet[15]);
                field(" efuse_valid=",packet[16]);field(" MAC_valid=",packet[17]);uart_puts("\n");
                result=0;goto done;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=5000){uart_puts("WIFI capability timeout\n");goto done;}
        vTaskDelay(1);
    }
done:
    uart_puts(result?"WIFI capability end status=failed\n":"WIFI capability end status=ready\n");
}
void sdio_wifi_scan(void){
    uart_puts("WIFI passive scan start channels=1..13\n");
    if(wifi_scan_unresolved){
        uart_puts("WIFI passive scan end status=refused-unresolved\n");return;
    }
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending ||
       wifi_management_pending || wifi_bench_active || wifi_sink_active){
        uart_puts("WIFI passive scan end status=refused-active\n");return;
    }
    int result=-1;unsigned activated=0,events=0,rx0_pending=0,complete=0,submitted=0;
    uint8_t scan_sequence=0;
    static uint8_t packet[4096];uint8_t active[12]={0};
    wifi_beacons=0;
    wifi_scan_cache_begin(&wifi_bss_cache);
    active[9]=1;activated=1; /* Track even an uncertain activation write. */
    if(control_set(0x15,active,sizeof active))goto done;
    uart_puts("WIFI scan AIS activation transferred; applied=unavailable\n");
    uint8_t command_packet[120];scan_sequence=wifi_sequence+1;
    if(!scan_sequence)scan_sequence=1;
    if(!wifi_scan_passive(command_packet,sizeof command_packet,scan_sequence,1,13))goto done;
    wifi_scan_active=1;
    submitted=1; /* A failed write may still have reached firmware. */
    field("WIFI scan request sequence=",scan_sequence);uart_puts("\n");
    if(control_send(0x1e,1,command_packet,sizeof command_packet))goto done;
    TickType_t start=xTaskGetTickCount(),completed=0;
    for(;;){
        uint32_t lengths;if(radio_read(0x50,&lengths))goto done;
        if((lengths&0xffff) && !rx0_pending){
            rx0_pending=lengths&0xffff;field("WIFI scan RX0 pending length=",rx0_pending);uart_puts("\n");
        }
        unsigned length;int got=event_read(packet,sizeof packet,&length);
        if(got<0)goto done;
        if(got){
            if(++events>128)goto done;
            if(packet[4]==0x15){
                if(complete || !wifi_scan_done(packet,length,scan_sequence)){
                    uart_puts("WIFI scan completion mismatch\n");goto done;
                }
                field("WIFI scan done sequence=",packet[8]);field(" RX0_pending=",rx0_pending);
                uart_puts("\n");complete=1;completed=xTaskGetTickCount();
            }
            if(packet[4]==1 && length>=12){
                field("WIFI command result id=",packet[8]);field(" status=",packet[9]);uart_puts("\n");
                if(packet[8]==0x1e && packet[9])goto done;
            }
        }
        /* RX1 completion can overtake raw beacons still queued in RX0. Read
         * both FIFOs after completion. Do not wait indefinitely for unrelated
         * frames on the last channel; cap the tail at one second. */
        if(complete){
            TickType_t elapsed=xTaskGetTickCount()-completed;
            if((!length && elapsed>=100) || elapsed>=1000){
                if(elapsed>=1000)uart_puts("WIFI scan tail status=bounded\n");
                result=0;goto done;
            }
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=10000){uart_puts("WIFI passive scan timeout\n");goto done;}
        vTaskDelay(1);
    }
done:
    if(submitted && !complete){
        uint8_t cancel[12];
        wifi_scan_unresolved=1;
        if(!wifi_scan_cancel(cancel,sizeof cancel,scan_sequence) ||
           control_set(0x1f,cancel,sizeof cancel)){
            uart_puts("WIFI scan cancellation status=failed\n");
        }else{
            field("WIFI scan cancellation transferred sequence=",scan_sequence);
            uart_puts(" applied=unavailable\n");
        }
        /* Transfer is not a firmware cancellation acknowledgement. Do not
         * silently start another scan or connection on unresolved state. */
        result=-1;
    }
    if(activated){
        uint8_t inactive[12]={0};
        if(control_set(0x15,inactive,sizeof inactive)){
            uart_puts("WIFI scan AIS cleanup status=failed\n");result=-1;
        }else uart_puts("WIFI scan AIS deactivation transferred; applied=unavailable\n");
    }
    field("WIFI scan received beacons=",wifi_beacons);uart_puts("\n");
    wifi_scan_active=0;
    wifi_scan_cache_finish(&wifi_bss_cache,result==0);
    uart_puts(result?"WIFI passive scan end status=failed\n":"WIFI passive scan end status=ready\n");
}
static unsigned ais_lease_left(TickType_t start,uint32_t interval){
    TickType_t elapsed=xTaskGetTickCount()-start;
    return elapsed>=interval?0:interval-elapsed;
}
static int ais_activate(const struct wifi_ais_beacon *selected,const struct wifi_ais_assoc *assoc,
    unsigned rcpi,TickType_t granted_at,uint32_t granted_ms){
    uint8_t bss[88],station[48],pm[20];
    if(!wifi_ais_join_prepare(&wifi_ais_connection,wifi_mac,selected,assoc,wifi_rate_profile,rcpi) ||
       !wifi_ais_join_bss(&wifi_ais_connection,bss,sizeof bss) ||
       !wifi_ais_join_station(&wifi_ais_connection,station,sizeof station) ||
       ais_lease_left(granted_at,granted_ms)<=2000)return -1;
    /* Fixed MT5931 reference nicConfigPowerSaveProfile: CID06, AIS0,
     * continuous active profile0. This is not CID25's advanced profile. */
    uint8_t cam[12]={0};wifi_ais_cam_attempted++;
    if(control_set(6,cam,sizeof cam))return -1;
    wifi_ais_cam_transferred++;
    uart_puts("WIFI AIS CAM network=00000000 profile=00000000 transferred; readback=unavailable\n");
    /* Fixed reference's normal supported filter: directed1, multicast2,
     * broadcast8. Clear P2P probe/action flags; no promiscuous mode. */
    uint8_t filter[12]={0};filter[8]=0x0b;
    if(control_set(0x0b,filter,sizeof filter))return -1;
    uart_puts("WIFI AIS RX filter=0000000b transferred; readback=unavailable\n");
    if(ais_lease_left(granted_at,granted_ms)<=1500)return -1;
    /* Receive hooks run during BSS and station credit waits. Do not discard
     * the first matching beacon just because activation has not arrived. */
    wifi_ais_join_watch(&wifi_ais_connection);
    if(control_set(0x16,bss,sizeof bss))return -1;
    uart_puts("WIFI AIS connected BSS transferred; applied=unavailable\n");
    if(ais_lease_left(granted_at,granted_ms)<=1000)return -1;
    if(control_set(0x17,station,sizeof station))return -1;
    uart_puts("WIFI AIS station state3 transferred; waiting activation and new beacon\n");
    static uint8_t packet[4096];
    while(ais_lease_left(granted_at,granted_ms)>500){
        unsigned length=0;
        if(event_read(packet,sizeof packet,&length)<0)return -1;
        if(wifi_ais_join_pm(&wifi_ais_connection,pm,sizeof pm)){
            field("WIFI AIS activated AID=",wifi_ais_connection.aid);
            field(" fresh beacon DTIM=",wifi_ais_connection.connected_beacon.dtim_period);
            uart_puts("\n");
            if(control_set(0x1a,pm,sizeof pm))return -1;
            uart_puts("WIFI AIS PM connected transferred; WPA2=unverified\n");
            return 0;
        }
        vTaskDelay(1);
    }
    field("WIFI AIS activation deadline activated=",wifi_ais_connection.activated);
    field(" fresh beacon=",wifi_ais_connection.beacon_seen);uart_puts("\n");
    /* These reads do not consume WTSR credits or read-clear WHISR bits. */
    uint32_t value;
    if(!radio_read(0,&value)){field("WIFI AIS deadline WCIR=",value);uart_puts("\n");}
    if(!radio_read(4,&value)){field("WIFI AIS deadline WHLPCR=",value);uart_puts("\n");}
    if(!radio_read(0x50,&value)){field("WIFI AIS deadline RX lengths=",value);uart_puts("\n");}
    return -1;
}
static int ais_association(const uint8_t *ap,const struct wifi_ais_beacon *selected,
    TickType_t granted_at,uint32_t granted_ms,unsigned connect,unsigned rcpi){
    uint8_t rsn[22];
    if(!wifi_ais_rsn_select(selected->rsn,selected->rsn_length,rsn,sizeof rsn))return -1;
    if(connect==2){
        uint8_t generated[22];
        if(wifi_wpa_radio_assoc_ie(generated,sizeof generated)!=sizeof generated)return -1;
        for(unsigned i=0;i<sizeof rsn;i++)if(generated[i]!=rsn[i])return -1;
        for(unsigned i=0;i<sizeof rsn;i++)rsn[i]=generated[i];
    }
    /* The reference synchronizes 1->1 and entry to state3, but 1->2 is a
     * host-only transition. Sending state2 as an update is not supported. */
    uart_puts("WIFI AIS station state2 host-only; firmware remains state1\n");
    uint8_t packet[128]={0};
    unsigned frame=wifi_ais_assoc_request(wifi_mac,ap,(++wifi_management_sequence)&4095,
        selected->capability&0x431,1,selected->ssid,selected->ssid_length,
        rsn,sizeof rsn,wifi_rate_profile,packet+16,sizeof packet-16);
    if(!frame || ais_lease_left(granted_at,granted_ms)<=1000 || tc4_wait() ||
       !ais_lease_left(granted_at,granted_ms))return -1;
    unsigned total=16+frame;
    packet[0]=(uint8_t)total;packet[1]=(uint8_t)(total>>8);
    packet[2]=20;packet[3]=0xd0;packet[4]=24;packet[5]=0x80;packet[11]=0x20;
    wifi_management_tx_sequence=(wifi_management_tx_sequence+1)&127;
    if(!wifi_management_tx_sequence)++wifi_management_tx_sequence;
    packet[12]=wifi_management_tx_sequence;packet[13]=5;
    if(tc4_write(packet,(total+3)&~3U))return -1;
    field("WIFI AIS association TX sequence=",packet[12]);uart_puts("\n");
    static uint8_t received[4096];
    unsigned tx_done=0,assoc_seen=0;struct wifi_ais_assoc accepted={0};
    while(ais_lease_left(granted_at,granted_ms)){
        unsigned length=0;int got=event_read(received,sizeof received,&length);
        if(got<0)return -1;
        if(got && length>=12 && received[4]==0x17 && received[8]==packet[12]){
            field("WIFI AIS association TXdone status=",received[9]);uart_puts("\n");
            if(received[9] || tx_done)return -1;
            tx_done=1;
        }
        unsigned offset=length>=12?12+(received[4]&3):0;
        struct wifi_ais_assoc assoc;
        if(offset && length>=offset+30 && (received[2]&3)==3 && received[5]==1 &&
           !(received[7]&0x80) && wifi_ais_assoc_response(received+offset,length-offset,
                wifi_mac,ap,wifi_rate_profile,&assoc)){
            field("WIFI AIS association response status=",assoc.status);
            field(" AID=",assoc.aid);field(" operational=",assoc.operational);
            field(" basic=",assoc.basic);uart_puts("\n");
            if(assoc.status)return -1;
            if(assoc_seen)return -1;
            accepted=assoc;accepted.ies=0;accepted.ie_length=0;assoc_seen=1;
        }
        if(tx_done && assoc_seen)return connect?ais_activate(selected,&accepted,rcpi,granted_at,granted_ms):0;
        vTaskDelay(1);
    }
    uart_puts("WIFI AIS association lease expired\n");return -1;
}
int sdio_wifi_wpa_select(unsigned channel,const unsigned char *ap,
    unsigned char *own,struct wifi_ais_beacon *selected){
    if(!ap || !own || !selected || !wifi_hif_ready || !wifi_mac_valid ||
       wifi_tx_fault || wifi_connection_unresolved || wifi_ap_active || wifi_peer_state ||
       wifi_peer_activate_pending || wifi_management_pending || wifi_bench_active ||
       wifi_sink_active || wifi_scan_active || wifi_scan_unresolved)return -1;
    uint8_t rcpi,rsn[22];
    if(!wifi_scan_cache_select(&wifi_bss_cache,xTaskGetTickCount(),5000,
        wifi_rate_profile,ap,channel,selected,&rcpi) || !selected->ssid_length ||
       !(selected->capability&16) ||
       !wifi_ais_rsn_select(selected->rsn,selected->rsn_length,rsn,sizeof rsn))return -1;
    for(unsigned i=0;i<6;i++)own[i]=wifi_mac[i];
    return 0;
}
struct ais_resources {
    uint8_t target[7],token;
    unsigned activated,requested,station_attempted,closed,failed;
};
static struct ais_resources ais_retained;
/* JOIN privilege is distinct from BSS/station ownership. Reserve a single
 * attempt before transfer; an uncertain abort must never be resubmitted. */
static int ais_release_join(struct ais_resources *r){
    if(!r)return -1;
    if(!r->requested)return r->failed?-1:0;
    if(r->token!=wifi_channel_token){
        r->failed=1;wifi_connection_unresolved=1;return -1;
    }
    uint8_t packet[28]={0};packet[9]=r->token;packet[10]=1;
    r->requested=0;
    if(control_set(0x20,packet,sizeof packet)){
        r->failed=1;wifi_connection_unresolved=1;return -1;
    }
    uart_puts("WIFI AIS JOIN privilege release transferred; applied=unavailable\n");return 0;
}
/* Retain per-attempt resources for eventual RSN ownership. Cleanup is called
 * once: repeating an uncertain command cannot establish hardware state. */
static int ais_cleanup(struct ais_resources *r){
    if(!r)return -1;
    if(r->closed)return r->failed?-1:0;
    r->closed=1;
    if(r->requested && r->token!=wifi_channel_token){
        r->failed=1;wifi_connection_unresolved=1;
        uart_puts("WIFI AIS cleanup token mismatch; HIF commands refused\n");return -1;
    }
    if(wifi_ais_connection.aid){
        unsigned owned=r->activated && r->station_attempted;
        for(unsigned i=0;i<6;i++)if(wifi_ais_connection.selected.ap[i]!=r->target[1+i])owned=0;
        if(!owned){
            r->failed=1;wifi_connection_unresolved=1;
            uart_puts("WIFI AIS cleanup owner mismatch; HIF commands refused\n");return -1;
        }
    }
    unsigned failed=r->failed;
    if(wifi_ais_connection.aid){
        /* Disable RX observation before removing this finite trial. PM abort
         * is attempted even when state3/PM submission may have failed. */
        wifi_ais_connection.watch=0;
        uint8_t pm_abort[12]={0};
        if(control_set(0x1b,pm_abort,sizeof pm_abort)){failed=1;}
        uint8_t bss[88];
        if(wifi_ais_join_bss(&wifi_ais_connection,bss,sizeof bss)){
            bss[9]=1;bss[56]=0xfe;
            if(control_set(0x16,bss,sizeof bss)){failed=1;}
        }else{failed=1;}
        wifi_ais_connection=(struct wifi_ais_join){0};
    }
    if(r->station_attempted){
        uint8_t remove[16]={0};
        for(unsigned i=0;i<6;i++)remove[10+i]=r->target[1+i];
        if(control_set(0x18,remove,sizeof remove)){failed=1;}
        else uart_puts("WIFI AIS station removal transferred; applied=unavailable\n");
    }
    if(ais_release_join(r))failed=1;
    if(r->activated){
        uint8_t inactive[12]={0};
        if(control_set(0x15,inactive,sizeof inactive)){failed=1;}
        else uart_puts("WIFI AIS channel deactivation transferred; applied=unavailable\n");
    }
    if(failed){
        wifi_connection_unresolved=1;
        uart_puts("WIFI AIS cleanup unresolved; subsequent HIF commands refused\n");
    }
    r->failed=failed;
    return failed?-1:0;
}
static int ais_run(unsigned authenticate,const uint8_t *provided){
    uart_puts(authenticate?"WIFI AIS auth probe start\n":"WIFI AIS channel probe start\n");
    if(wifi_ais_retained_active || !wifi_hif_ready || wifi_tx_fault || wifi_connection_unresolved || wifi_ap_active || wifi_peer_state ||
       wifi_peer_activate_pending || wifi_management_pending ||
       wifi_bench_active || wifi_sink_active || wifi_scan_active || wifi_scan_unresolved ||
       (authenticate && !wifi_mac_valid)){
        uart_puts(authenticate?"WIFI AIS auth probe end status=refused-active\n":
            "WIFI AIS channel probe end status=refused-active\n");return -1;
    }
    uart_puts(authenticate?"WIFI AIS auth target bytes=7\n":"WIFI AIS channel target bytes=7\n");
    uint8_t target[7],command[28],active[12]={0};unsigned used=0;
    TickType_t input_start=xTaskGetTickCount();
    if(provided){for(unsigned i=0;i<7;i++)target[i]=provided[i];used=7;}
    while(used<sizeof target){
        int c=uart_getc();if(c>=0)target[used++]=(uint8_t)c;
        else vTaskDelay(1);
        if((TickType_t)(xTaskGetTickCount()-input_start)>=3000){
            uart_puts(authenticate?"WIFI AIS auth probe end status=input-timeout\n":
                "WIFI AIS channel probe end status=input-timeout\n");return -1;
        }
    }
    /* Build before any radio mutation. Network0 JOIN, explicit AP and channel. */
    uint8_t token=wifi_channel_token+1;if(!token)token=1;
    if(!wifi_channel_request_ais(command,sizeof command,target[0],token,5000,target+1)){
        uart_puts(authenticate?"WIFI AIS auth probe end status=invalid-target\n":
            "WIFI AIS channel probe end status=invalid-target\n");return -1;
    }
    uint8_t response[48]={0};
    if(authenticate && !wifi_ais_auth_request(wifi_mac,target+1,
        (++wifi_management_sequence)&4095,response+16,sizeof response-16)){
        uart_puts("WIFI AIS auth probe end status=invalid-target\n");return -1;
    }
    static struct wifi_ais_beacon selected;
    uint8_t rcpi=0;
    if(authenticate && !wifi_scan_cache_select(&wifi_bss_cache,xTaskGetTickCount(),5000,
        wifi_rate_profile,target+1,target[0],&selected,&rcpi)){
        uart_puts("WIFI AIS auth scan cache missing-or-stale\n");
        uart_puts("WIFI AIS auth probe end status=failed\n");return -1;
    }
    if(authenticate>=2){
        uint8_t rsn[22];
        if(!selected.ssid_length || !(selected.capability&16) ||
           !wifi_ais_rsn_select(selected.rsn,selected.rsn_length,rsn,sizeof rsn)){
            uart_puts("WIFI AIS auth probe end status=unsupported-rsn\n");return -1;
        }
    }
    if(authenticate==4 && wifi_wpa_radio_validate(wifi_mac,&selected)){
        uart_puts("WIFI AIS RSN owner mismatch; no radio mutation\n");return -1;
    }
    int result=-1;unsigned activated=1,requested=0,station_attempted=0;uint32_t granted_ms=0;
    TickType_t granted_at=0;
    static uint8_t received[4096];
    active[9]=1;
    if(control_set(0x15,active,sizeof active))goto done;
    wifi_channel_token=token;requested=1;
    if(control_send(0x20,1,command,sizeof command))goto done;
    TickType_t start=xTaskGetTickCount();unsigned events=0;
    for(;;){
        unsigned length;int got=event_read(received,sizeof received,&length);
        if(got<0)goto done;
        if(got){
            if(++events>128)goto done;
            if(received[4]==0x18){
                if(!wifi_channel_grant_ais(received,length,target[0],token,&granted_ms)){
                    uart_puts("WIFI AIS channel grant mismatch\n");goto done;
                }
                field("WIFI AIS channel granted channel=",target[0]);
                field(" token=",token);field(" interval_ms=",granted_ms);uart_puts("\n");
                granted_at=xTaskGetTickCount();
                if(authenticate)goto authentication;
                result=0;goto done;
            }
            if(received[4]==1 && received[5]==wifi_sequence &&
               (length<12 || received[8]!=0x20 || received[9]))goto done;
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=3000){
            uart_puts("WIFI AIS channel grant timeout\n");goto done;
        }
        vTaskDelay(1);
    }
authentication:;
    /* JOIN uses the validated scan descriptor. Another beacon is not
     * guaranteed after the channel grant; keep cache age and lease guards. */
    uart_puts("WIFI AIS selected beacon source=completed-scan-cache\n");
    if(!wifi_scan_cache_select(&wifi_bss_cache,xTaskGetTickCount(),5000,
        wifi_rate_profile,target+1,target[0],&selected,&rcpi)){
        uart_puts("WIFI AIS cached beacon expired before authentication\n");goto done;
    }
    struct wifi_station_config station={0};
    for(unsigned i=0;i<6;i++)station.peer[i]=target[1+i];
    station.listen=1;station.operational=selected.operational;station.basic=selected.basic;
    station.phy=(selected.operational&15)?3:2;station.state=1;station.rcpi=rcpi;
    uint8_t station_packet[48];
    if(!wifi_station_pack(station_packet,sizeof station_packet,&station))goto done;
    if(ais_lease_left(granted_at,granted_ms)<=1000)goto done;
    station_attempted=1;
    if(control_set(0x17,station_packet,sizeof station_packet))goto done;
    uart_puts("WIFI AIS station state1 transferred; applied=unavailable\n");
    if(ais_lease_left(granted_at,granted_ms)<=1000 || tc4_wait())goto done;
    if(!ais_lease_left(granted_at,granted_ms))goto done;
    /* Native 802.11 management, TC4, AIS0, station0, basic rate, TXdone tag.
     * Do not use control_send: it replaces the completed HIF header. */
    response[0]=46;response[2]=20;response[3]=0xd0;response[4]=24;
    response[5]=0x80;response[11]=0x20;
    wifi_management_tx_sequence=(wifi_management_tx_sequence+1)&127;
    if(!wifi_management_tx_sequence)++wifi_management_tx_sequence;
    response[12]=wifi_management_tx_sequence;response[13]=5;
    if(tc4_write(response,sizeof response))goto done;
    field("WIFI AIS authentication TX sequence=",response[12]);uart_puts("\n");
    unsigned tx_done=0,auth_seen=0;
    while(ais_lease_left(granted_at,granted_ms)){
        unsigned length;int got=event_read(received,sizeof received,&length);
        if(got<0)goto done;
        if(got && received[4]==0x17 && length>=12 && received[8]==response[12]){
            field("WIFI AIS authentication TXdone status=",received[9]);uart_puts("\n");
            if(received[9] || tx_done)goto done;
            tx_done=1;
        }
        unsigned offset=12+(received[4]&3);uint16_t auth_status;
        if(length>=offset+30 && (received[2]&3)==3 && received[5]==1 &&
           !(received[7]&0x80) && wifi_ais_auth_response(received+offset,length-offset,
               wifi_mac,target+1,&auth_status)){
            field("WIFI AIS authentication response status=",auth_status);uart_puts("\n");
            if(auth_status)goto done;
            auth_seen=1;
        }
        if(tx_done && auth_seen){
            result=authenticate>=2?ais_association(target+1,&selected,granted_at,granted_ms,authenticate==4?2:authenticate==3,rcpi):0;
            goto done;
        }
        vTaskDelay(1);
    }
    uart_puts("WIFI AIS authentication lease expired\n");
done:;
    struct ais_resources resources={0};
    for(unsigned i=0;i<7;i++)resources.target[i]=target[i];
    resources.token=token;resources.activated=activated;resources.requested=requested;
    resources.station_attempted=station_attempted;
    if(authenticate==4 && !result){
        if(!ais_release_join(&resources)){
            ais_retained=resources;wifi_ais_retained_active=1;
            uart_puts("WIFI AIS retained association ready; WPA2=unverified\n");return 0;
        }
        result=-1;
    }
    if(ais_cleanup(&resources))result=-1;
    if(authenticate==4)ais_retained=resources;
    if(authenticate)uart_puts(result?"WIFI AIS auth probe end status=failed\n":
        "WIFI AIS auth probe end status=ready\n");
    else uart_puts(result?"WIFI AIS channel probe end status=failed\n":
        "WIFI AIS channel probe end status=ready\n");
    return result;
}
static int ais_probe(unsigned authenticate){return ais_run(authenticate,0);}
int sdio_wifi_wpa_join(const unsigned char *target){
    if(!target)return -1;
    return ais_run(4,target);
}
int sdio_wifi_wpa_leave(void){
    if(!wifi_ais_retained_active)return ais_retained.failed?-1:0;
    wifi_ais_retained_teardown=1;
    int result=ais_cleanup(&ais_retained);
    wifi_ais_retained_teardown=0;wifi_ais_retained_active=0;
    return result;
}
unsigned sdio_wifi_milliseconds(void){return xTaskGetTickCount();}
void sdio_wifi_ais_channel_probe(void){ais_probe(0);}
void sdio_wifi_ais_auth_probe(void){ais_probe(1);}
void sdio_wifi_ais_assoc_probe(void){
    uart_puts("WIFI AIS association trial start; includes authentication\n");
    int result=ais_probe(2);
    uart_puts(result?"WIFI AIS association trial end status=failed\n":
        "WIFI AIS association trial end status=ready\n");
}
void sdio_wifi_ais_connect_probe(void){
    uart_puts("WIFI AIS connection trial start; WPA2 not implemented\n");
    int result=ais_probe(3);
    uart_puts(result?"WIFI AIS connection trial end status=failed\n":
        "WIFI AIS connection trial end status=ready\n");
}
static int control_set(unsigned cid,uint8_t *packet,unsigned length){
    if(control_send(cid,1,packet,length))return -1;
    uint8_t sequence=wifi_sequence;static uint8_t received[4096];
    TickType_t start=xTaskGetTickCount();
    for(;;){
        unsigned received_length;int got=event_read(received,sizeof received,&received_length);
        if(got<0)return -1;
        if(got && received[4]==1 && received[5]==sequence){
            if(received_length<12 || received[8]!=cid)return -1;
            field("WIFI set result cid=",cid);field(" status=",received[9]);uart_puts("\n");
            if(received[9])return -1;
        }
        /* These set commands do not request a response in the reference
         * driver. Credit return proves transfer, not parameter readback. */
        if(wifi_tc4_free==4){field("WIFI set transferred cid=",cid);uart_puts("\n");return 0;}
        if((TickType_t)(xTaskGetTickCount()-start)>=1000){uart_puts("WIFI set credit timeout\n");return -1;}
        vTaskDelay(1);
    }
}
int sdio_wifi_wpa_key_submit(const unsigned char *body,unsigned n){
    if(!body || n!=64 || !wifi_hif_ready || !wifi_mac_valid || wifi_tx_fault ||
       wifi_connection_unresolved || wifi_ap_active || wifi_peer_state ||
       !wifi_ais_connection.watch || !wifi_ais_connection.activated ||
       !wifi_ais_connection.beacon_seen || !wifi_ais_connection.aid ||
       body[0]>1 || body[1]>1 || body[2]>1 || body[3] || body[10] ||
       body[12]>3 || body[14] || body[15])return -1;
    unsigned peer=1,broadcast=1;
    for(unsigned i=0;i<6;i++){
        if(body[4+i]!=wifi_ais_connection.selected.ap[i])peer=0;
        if(body[4+i]!=255)broadcast=0;
    }
    if(body[2] ? (!peer || body[12]) : (!peer && !broadcast))return -1;
    if(body[0]){
        if(body[11]!=4 || body[13]!=16 || body[1]!=body[2])return -1;
        /* Remaining key material and RSC must be zero. Nonzero CCMP RSC
         * mapping is unverified; the WAPI16-byte PN branch is not evidence. */
        for(unsigned i=32;i<64;i++)if(body[i])return -1;
    }else{
        if(body[1] || body[11] || body[13])return -1;
        for(unsigned i=16;i<64;i++)if(body[i])return -1;
    }
    uint8_t command[72]={0};
    for(unsigned i=0;i<64;i++)command[8+i]=body[i];
    /* Public driver submits CID08 without requesting a response. Treat the
     * existing credit wait as transfer only, never fabricate a key ACK. */
    int result=control_set(8,command,sizeof command);
    volatile uint8_t *wipe=command;
    for(unsigned i=0;i<sizeof command;i++)wipe[i]=0;
    if(result)wifi_connection_unresolved=1;
    return result;
}
void sdio_wifi_osc(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending ||
       wifi_management_pending || wifi_data_count || tuner_ts_stream_active() ||
       wifi_ais_retained_active || wifi_connection_unresolved){
        uart_puts("WIFI OSC end status=refused-active\n");return;
    }
    if(wifi_osc_attempted){uart_puts("WIFI OSC end status=refused-attempted\n");return;}
    if(!wifi_hif_ready || wifi_tx_fault || tx_poll() ||
       wifi_tc1_free!=14 || wifi_tc2_free!=1 || wifi_tc3_free!=1 ||
       wifi_tc4_free!=4 || wifi_tc5_free!=1){
        uart_puts("WIFI OSC end status=refused-state\n");return;
    }
    /* MT5931 SET_OSC: prefix8 + little-endian stable time0 + reserved6.
     * The Linux initialization uses zero. Credit return is not readback. */
    uint8_t packet[16]={0};
    wifi_osc_attempted=1;
    if(control_set(0xf2,packet,sizeof packet)){
        uart_puts("WIFI OSC end status=failed\n");return;
    }
    uart_puts("WIFI OSC stable_time=00000000 readback=unavailable\n");
    uart_puts("WIFI OSC end status=transferred\n");
}
void sdio_wifi_board(void){
    wifi_board_sent=0;
    uart_puts("WIFI board configuration start\n");
    uint8_t power[48]={0},phy[152]={0},domain[64]={0};
    for(unsigned i=0;i<40;i++)power[i+8]=wifi_board_tx_power[i];
    /* Factory PHY override is 144 zero bytes. No guessed calibration values.
     * Explicit JP, 2.4GHz channels1..13, 20MHz; unused subbands disabled. */
    domain[8]='P';domain[9]='J';
    domain[12]=81;domain[13]=1;domain[14]=1;domain[15]=1;domain[16]=13;
    domain[60]=domain[61]=1;
    if(control_set(0x28,power,sizeof power) || control_set(0x31,phy,sizeof phy) ||
       control_set(0x13,domain,sizeof domain)){
        uart_puts("WIFI board configuration end status=failed\n");return;
    }
    uart_puts("WIFI board configuration end status=transferred\n");
    wifi_board_sent=1;
}
void sdio_wifi_auto_per(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending ||
       wifi_management_pending || wifi_data_count || tuner_ts_stream_active()){
        uart_puts("WIFI auto PER end status=refused-active\n");return;
    }
    if(wifi_per_attempted){uart_puts("WIFI auto PER end status=refused-attempted\n");return;}
    if(!wifi_hif_ready || !wifi_board_sent || wifi_tx_fault || tx_poll() ||
       wifi_tc1_free!=14 || wifi_tc2_free!=1 || wifi_tc3_free!=1 ||
       wifi_tc4_free!=4 || wifi_tc5_free!=1){
        uart_puts("WIFI auto PER end status=refused-state\n");return;
    }
    wifi_per_attempted=1;
    for(unsigned step=0;step<8;step++){
        uint8_t packet[16];
        if(!wifi_auto_per_command(packet,sizeof packet,step) || control_set(0xc2,packet,sizeof packet)){
            field("WIFI auto PER transferred_steps=",wifi_per_steps);uart_puts("\n");
            uart_puts("WIFI auto PER end status=failed\n");return;
        }
        wifi_per_steps++;
        field("WIFI auto PER transferred_step=",wifi_per_steps);uart_puts("\n");
    }
    wifi_per_transferred=1;
    uart_puts("WIFI auto PER enable=00000001 algorithm=00000001 HT_clear=00000000 legacy_clear=00000000 applied=unavailable\n");
    uart_puts("WIFI auto PER end status=transferred\n");
}
void sdio_wifi_dpd(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending ||
       wifi_management_pending || wifi_data_count){
        uart_puts("WIFI DPD request end status=refused-active\n");return;
    }
    if(wifi_dpd_attempted){
        uart_puts("WIFI DPD request end status=refused-attempted\n");return;
    }
    if(!wifi_hif_ready || !wifi_board_sent || wifi_tx_fault || tx_poll() ||
       wifi_tc1_free!=14 || wifi_tc2_free!=1 || wifi_tc3_free!=1 ||
       wifi_tc4_free!=4 || wifi_tc5_free!=1){
        uart_puts("WIFI DPD request end status=refused-state\n");return;
    }
    /* Independent PTA envelope: command prefix8 + body24, parameters at
     * body offset4. Unused envelope bytes are explicitly zero. */
    uint8_t packet[32]={0};packet[13]=1;packet[15]=0x80;
    /* A failed transfer may already have reached the radio. No automatic
     * retry; transfer confirmation is not calibration completion. */
    wifi_dpd_attempted=1;
    if(control_set(0xf1,packet,sizeof packet)){
        uart_puts("WIFI DPD request end status=failed\n");return;
    }
    wifi_dpd_transferred=1;
    uart_puts("WIFI DPD request body_bytes=00000018 param_offset=00000004 param=00010080 completion=unavailable\n");
    uart_puts("WIFI DPD request end status=transferred\n");
}
void sdio_wifi_ap_stop(void){
    sdio_wifi_tx_bench_stop();
    if(wifi_sink_active){wifi_sink_end=xTaskGetTickCount();wifi_sink_active=0;}
    uart_puts("WIFI AP stop start\n");
    wifi_ap_stop_ok=0;
    wifi_ap_active=0;
    wifi_management_length=0;
    wifi_data_head=wifi_data_count=0;
    wifi_management_pending=wifi_management_done=0;
    wifi_peer_active=wifi_peer_activated=wifi_peer_activate_pending=0;
    wifi_peer_ht=(struct wifi_ht_peer){0};
    if(wifi_peer_state){
        uint8_t remove[16]={0};
        for(unsigned i=0;i<6;i++)remove[10+i]=wifi_peer[i];
        if(control_set(0x18,remove,sizeof remove)){
            uart_puts("WIFI AP stop end status=failed\n");return;
        }
        wifi_peer_state=0;
    }
    uint8_t abort_packet[12]={0},inactive[12]={0},channel_abort[28]={0};
    abort_packet[8]=inactive[8]=1;
    channel_abort[8]=1;channel_abort[9]=wifi_channel_token;channel_abort[10]=1;
    if(control_set(0x1b,abort_packet,sizeof abort_packet) ||
       control_set(0x20,channel_abort,sizeof channel_abort) ||
       control_set(0x15,inactive,sizeof inactive)){
        uart_puts("WIFI AP stop end status=failed\n");return;
    }
    uart_puts("WIFI AP stop end status=transferred\n");
    wifi_ap_stop_ok=1;
}
void sdio_wifi_quiesce(void){
    if(!wifi_hif_ready || (!wifi_ap_active && !wifi_peer_state)){
        uart_puts("WIFI recovery stop status=inactive\n");return;
    }
    sdio_wifi_ap_stop();
    uart_puts(wifi_ap_stop_ok?"WIFI recovery stop status=transferred\n":
        "WIFI recovery stop status=failed\n");
}
void sdio_wifi_ap(void){
    uart_puts("WIFI AP start\n");
    if(wifi_scan_unresolved){
        uart_puts("WIFI AP end status=refused-unresolved\n");return;
    }
    const struct wifi_rates *rates=wifi_rates_get(wifi_rate_profile);
    field("WIFI AP rate profile=",wifi_rate_profile);field(" operational=",rates->operational);
    field(" basic=",rates->basic);field(" phy=",rates->phy);uart_puts("\n");
    sdio_wifi_ap_stop();
    if(!wifi_ap_stop_ok)goto failed;
    wifi_data_rx=wifi_data_tx=wifi_data_dropped=0;
    wifi_power_events_reset(&wifi_power);
    sdio_wifi_board();if(!wifi_board_sent)goto failed;
    sdio_wifi_mac();if(!wifi_mac_valid)goto failed;
    uint8_t active[12]={0},channel[28]={0},bss[88]={0},created[16]={0};
    /* Restore the device role before asking for a new GO/AP channel, matching
     * the reference's sync-to-firmware path when leaving AP mode. A retained
     * radio still has the previous AP BSS after only the MCU RAM is replaced. */
    bss[8]=1;bss[9]=1;bss[10]=3;bss[56]=0xfe;
    bss[59]=1;bss[61]=1;bss[62]=rates->phy;
    for(unsigned i=0;i<6;i++){bss[44+i]=wifi_mac[i];bss[63+i]=wifi_mac[i];}
    bss[72]=1;bss[73]=1;bss[74]=wifi_ap_channel;bss[86]=1;bss[87]=0x72;
    if(control_set(0x16,bss,sizeof bss))goto failed;
    uart_puts("WIFI AP prior BSS role=device transferred\n");
    /* p2pFuncSwitchOPMode also resets the internal P2P role. The public
     * P2P_DISCONNECT_INFO wire body is exactly four bytes: role2 + reserved. */
    uint8_t p2p_abort[12]={0};p2p_abort[8]=2;
    if(control_set(0x2b,p2p_abort,sizeof p2p_abort))goto failed;
    uart_puts("WIFI AP prior P2P role aborted\n");
    active[8]=1;active[9]=1;
    if(control_set(0x15,active,sizeof active))goto failed;
    /* Network1, JOIN channel request, 2.4GHz, no secondary channel. */
    if(!++wifi_channel_token)++wifi_channel_token;
    if(!wifi_channel_request_ap(channel,sizeof channel,wifi_ap_channel,wifi_channel_token,wifi_channel_bssid_mode,wifi_mac))goto failed;
    field("WIFI AP channel request BSSID mode=",wifi_channel_bssid_mode);uart_puts("\n");
    if(control_send(0x20,1,channel,sizeof channel))goto failed;
    TickType_t start=xTaskGetTickCount();static uint8_t received[4096];
    for(;;){
        unsigned length;int got=event_read(received,sizeof received,&length);
        if(got<0)goto failed;
        if(got && received[4]==0x18){
            if(!wifi_channel_grant(received,length,wifi_ap_channel,wifi_channel_token))goto failed;
            uart_puts("WIFI AP channel granted\n");break;
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=3000){uart_puts("WIFI AP channel timeout\n");goto failed;}
        vTaskDelay(1);
    }
    static const uint8_t ssid[6]={'T','U','V','L','0','1'};
    bss[8]=1;bss[9]=1;bss[10]=2;bss[11]=sizeof ssid;
    for(unsigned i=0;i<sizeof ssid;i++)bss[12+i]=ssid[i];
    for(unsigned i=0;i<6;i++){bss[44+i]=wifi_mac[i];bss[63+i]=wifi_mac[i];}
    bss[52]=rates->operational;bss[53]=rates->operational>>8;
    bss[54]=rates->basic;bss[55]=rates->basic>>8;
    bss[56]=0xfe;bss[59]=1;bss[61]=1;bss[62]=rates->phy;bss[70]=1;
    bss[72]=1;bss[73]=1;bss[74]=wifi_ap_channel;bss[86]=1;bss[87]=0x72;
    uint8_t queues[52];
    if(wifi_ht_enabled){
        bss[50]=1;bss[62]|=WIFI_PHY_HT;bss[77]=3;bss[82]=3;
        uint8_t ampdu[12]={0},reject[12]={0};reject[8]=1;
        if(control_set(0x23,ampdu,sizeof ampdu) || control_set(0x24,reject,sizeof reject))goto failed;
        uart_puts("WIFI HT aggregation disabled; RX ADDBA rejection transferred\n");
    }
    if(!(wifi_ht_enabled?wifi_ht_queues(queues,sizeof queues):wifi_queue_pack(queues,sizeof queues,wifi_queue_mode)) ||
       control_set(0x21,queues,sizeof queues))goto failed;
    field("WIFI AP queue parameters transferred mode=",wifi_queue_mode);uart_puts("\n");
    if(control_set(0x16,bss,sizeof bss))goto failed;
    uint8_t ies[128];unsigned ie_length=wifi_rates_ies_channel(wifi_rate_profile,1,wifi_ap_channel,ies,sizeof ies);
    if(!ie_length)goto failed;
    if(wifi_ht_enabled){
        unsigned extra=wifi_ht_ies(ies+ie_length,sizeof ies-ie_length,wifi_ap_channel,1,1);
        if(!extra)goto failed;
        ie_length+=extra;
    }
    uint8_t beacon[144];unsigned beacon_length=wifi_beacon_pack(beacon,sizeof beacon,ies,ie_length);
    if(!beacon_length || control_set(0x1c,beacon,beacon_length))goto failed;
    created[8]=1;created[9]=1;created[10]=100;
    if(control_set(0x19,created,sizeof created))goto failed;
    uint8_t filter[12]={0};filter[8]=9;filter[11]=0x80;
    if(control_set(0x0b,filter,sizeof filter))goto failed;
    for(unsigned i=0;i<sizeof bss;i++)wifi_ap_bss[i]=bss[i];
    wifi_ap_active=1;
    field("WIFI AP SSID=TUVL01 channel=",wifi_ap_channel);uart_puts(" open; single-peer association\n");
    uart_puts("WIFI AP end status=transferred\n");return;
failed:
    sdio_wifi_ap_stop();
    uart_puts("WIFI AP end status=failed\n");
}
void sdio_wifi_rate(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI rate end status=refused-active\n");return;
    }
    if(wifi_fixed_mcs){uart_puts("WIFI rate end status=refused-fixed-mcs\n");return;}
    wifi_fixed54=(wifi_fixed54+1)%3;
    field("WIFI fixed54 selected=",wifi_fixed54);uart_puts("\n");
    uart_puts("WIFI rate end status=selected\n");
}
void sdio_wifi_cam(void){
    if(wifi_peer_state || wifi_peer_activate_pending || wifi_management_pending){
        uart_puts("WIFI CAM end status=refused-peer\n");return;
    }
    if(!wifi_ap_active || !wifi_hif_ready || wifi_tx_fault || tx_poll() ||
       wifi_tc1_free!=14 || wifi_tc4_free!=4 || wifi_tc5_free!=1){
        uart_puts("WIFI CAM end status=refused-state\n");return;
    }
    /* Four-byte CMD_PS_PROFILE body: network 1, CAM 0, reserved zero.
     * Credit return confirms delivery; there is no parameter readback. */
    uint8_t packet[12]={0};packet[8]=1;
    if(control_set(6,packet,sizeof packet)){
        uart_puts("WIFI CAM end status=failed\n");return;
    }
    uart_puts("WIFI CAM network=00000001 profile=00000000 readback=unavailable\n");
    uart_puts("WIFI CAM end status=transferred\n");
}
void sdio_wifi_rate_profile(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI rate profile end status=refused-active\n");return;
    }
    wifi_rate_profile^=1;
    field("WIFI rate profile selected=",wifi_rate_profile);uart_puts("\nWIFI rate profile end status=selected\n");
}
static int station_update(unsigned state,unsigned associated){
    const struct wifi_rates *rates=wifi_rates_get(wifi_rate_profile);
    if(!rates || state<1 || state>3)return -1;
    struct wifi_station_config config={0};
    for(unsigned i=0;i<6;i++)config.peer[i]=wifi_peer[i];
    config.aid=associated?1:0;config.listen=wifi_peer_listen;
    config.network=1;config.phy=rates->phy;config.state=(uint8_t)state;
    config.operational=wifi_peer_rates;config.basic=rates->basic;
    config.rcpi=wifi_peer_rcpi; /* measured HIF RX RCPI, initial auto-rate input */
    uint8_t command_packet[48];
    if(!wifi_station_pack(command_packet,sizeof command_packet,&config))return -1;
    if(wifi_ht_enabled && associated && !wifi_ht_station(command_packet,sizeof command_packet,&wifi_peer_ht))return -1;
    if(associated && !wifi_fixed_rate_apply(command_packet,sizeof command_packet,wifi_fixed54,wifi_fixed_mcs,&wifi_peer_ht))return -1;
    if(control_set(0x17,command_packet,sizeof command_packet))return -1;
    field("WIFI station state transferred=",state);uart_puts("\n");return 0;
}
/* Limit TS outstanding frames without inventing or refunding radio credits.
 * Non-TS unicast replies still consume TC1 and reduce the available window. */
static unsigned ts_window_slots(void){
    unsigned held=14-wifi_tc1_free;
    if(wifi_tc1_free>14 || held>=wifi_ts_window){wifi_window_stalls++;return 0;}
    return wifi_ts_window-held;
}
int sdio_wifi_ts_pair(const unsigned char *data,unsigned count,unsigned sequence,unsigned index,unsigned flags){
    static uint8_t packet[3072];
    if(!data || !count || count>14 || sdio_wifi_raw_tx_selected())return -1;
    if(!wifi_ap_active || !wifi_peer_active || wifi_tx_fault)return 0;
    /* Reuse only this service loop's validated positive balance, as for
     * single frames. Each contained HIF frame still reserves one credit. */
    if(data_credit(wifi_tc1_free))return -1;
    unsigned slots=ts_window_slots();
    if(!slots)return 0;
    if(slots==1 && count>7)count=7;
    unsigned frames=(count+6)/7;
    unsigned length=wifi_ts_tx_pack_forwarding(data,count,sequence,index,flags,
        wifi_mac,wifi_peer,packet,sizeof packet,wifi_more_data);
    if(!length)return -1;
    /* Mode2 compares the station restriction with HIF basic-rate forcing.
     * Modify each packed frame, preserving the explicit zero terminator. */
    if(wifi_fixed54==2){
        unsigned offset=0;
        for(unsigned frame=0;frame<frames;frame++){
            packet[offset+13]|=4;
            unsigned logical=packet[offset]|((unsigned)packet[offset+1]<<8);
            offset+=(logical+3)&~3U;
        }
    }
    uint8_t feedback_tags[2]={0};
    if(wifi_feedback_enabled){
        unsigned offset=0,remaining=count;
        for(unsigned frame=0;frame<frames;frame++){
            unsigned frame_count=remaining>7?7:remaining;
            uint32_t frame_sequence=sequence+frame;
            if(!(frame_sequence&15U) &&
               wifi_tx_feedback_reserve(&wifi_feedback,frame_sequence,&feedback_tags[frame])){
                packet[offset+12]=feedback_tags[frame];packet[offset+13]|=1;
                if(wifi_timing_enabled)wifi_tx_timing_sample(&wifi_timing,
                    feedback_tags[frame],frame_count,xTaskGetTickCount());
            }
            unsigned logical=packet[offset]|((unsigned)packet[offset+1]<<8);
            offset+=(logical+3)&~3U;remaining-=frame_count;
        }
    }
    wifi_tc1_free-=frames;
    uint32_t io_begin=wifi_io.active?board_time_counts():0;
    int io_result=extended_write(0x28,packet,length,0);
    if(wifi_io.active)wifi_io_record(&wifi_io,WIFI_IO_TS_WRITE,length,io_begin,board_time_counts(),io_result!=0);
    if(io_result){
        /* Write completion is uncertain: do not restore credits or retry. */
        for(unsigned frame=0;frame<frames;frame++)if(feedback_tags[frame]){
            wifi_tx_feedback_cancel(&wifi_feedback,feedback_tags[frame]);
            if(wifi_timing_enabled)wifi_tx_timing_cancel(&wifi_timing,feedback_tags[frame]);
        }
        wifi_tx_fault=1;return -1;
    }
    wifi_data_tx+=frames;return (int)count;
}
int sdio_wifi_ts(const unsigned char *data,unsigned count,unsigned sequence,unsigned index,unsigned flags){
    static uint8_t packet[1536],raw_packet[1536];
    uint8_t *body=packet+16+42;
    if(!data || !count || count>7)return -1;
    if(!wifi_ap_active || !wifi_peer_active || wifi_tx_fault)return 0;
    if(sdio_wifi_raw_tx_selected()==2 && (!wifi_ht_enabled || !wifi_ht_active(&wifi_peer_ht)))return -1;
    unsigned tc=sdio_wifi_raw_tx_selected()==2?wifi_qos_tc:1;
    unsigned *credit=tc==2?&wifi_tc2_free:tc==3?&wifi_tc3_free:&wifi_tc1_free;
    if(tc!=1 && (tc>3 || wifi_timing_enabled))return -1;
    if(data_credit(*credit))return -1;
    if(tc==1){if(!ts_window_slots())return 0;}
    else if(!*credit){++wifi_window_stalls;return 0;}
    else if(*credit>1){wifi_tx_fault=1;return -1;}
    body[0]='T';body[1]='T';body[2]='S';body[3]='1';
    unsigned fields[3]={sequence,index,flags};
    for(unsigned n=0;n<3;n++)for(unsigned b=0;b<4;b++)body[4+n*4+b]=fields[n]>>(24-b*8);
    for(unsigned n=0;n<count*188;n++)body[16+n]=data[n];
    unsigned length=wifi_net_udp(body,16+count*188,4202,wifi_mac,wifi_peer,packet+16,sizeof packet-16);
    if(!length)return -1;
    unsigned logical=16+length,padded=(logical+3)&~3U;
    if(padded>512)padded=(padded+511)&~511U;
    for(unsigned n=logical;n<padded;n++)packet[n]=0;
    for(unsigned n=0;n<16;n++)packet[n]=0;
    packet[0]=logical;packet[1]=logical>>8;packet[2]=14;packet[3]=1<<2;
    packet[4]=14;packet[5]=0x10;packet[11]=0x20;
    uint8_t *wire=packet;
    if(sdio_wifi_raw_tx_selected()){
        padded=sdio_wifi_raw_tx_selected()==2?
            wifi_raw_qos_class_tx_pack(packet+16,length,wifi_mac,sequence,raw_packet,sizeof raw_packet,tc==2?4:tc==3?6:0,tc):
            wifi_raw_tx_pack(packet+16,length,wifi_mac,sequence,raw_packet,sizeof raw_packet);
        if(!padded)return -1;
        wire=raw_packet;
    }
    uint8_t feedback_tag=0;
    unsigned feedback=wifi_feedback_enabled && !(sequence&15U) &&
        wifi_tx_feedback_reserve(&wifi_feedback,sequence,&feedback_tag);
    if(feedback){wire[12]=feedback_tag;wire[13]=1;}
    if(wifi_fixed54==2)wire[13]|=4;
    if(wifi_timing_enabled){
        uint32_t now=xTaskGetTickCount();
        if(wifi_ts_window==1 && wifi_tc1_free==14)wifi_tx_timing_begin(&wifi_timing,count,now);
        if(feedback)wifi_tx_timing_sample(&wifi_timing,feedback_tag,count,now);
    }
    --*credit;
    uint32_t io_begin=wifi_io.active?board_time_counts():0;
    int io_result=extended_write(0x28,wire,padded,0);
    if(wifi_io.active)wifi_io_record(&wifi_io,WIFI_IO_TS_WRITE,padded,io_begin,board_time_counts(),io_result!=0);
    if(io_result){
        if(feedback)wifi_tx_feedback_cancel(&wifi_feedback,feedback_tag);
        if(wifi_timing_enabled)wifi_tx_timing_cancel(&wifi_timing,feedback_tag);
        wifi_tx_fault=1;return -1;
    }
    if(wifi_timing_enabled)wifi_tx_timing_written(&wifi_timing,xTaskGetTickCount());
    ++wifi_data_tx;return 1;
}
static int data_reply(void){
    if(!wifi_peer_active || !wifi_data_count)return 0;
    static uint8_t packet[1536];
    unsigned slot=wifi_data_head;
    unsigned length=wifi_net_reply(wifi_data[slot],wifi_data_lengths[slot],
                                  wifi_mac,wifi_peer,packet+16,sizeof packet-16);
    if(!length){wifi_data_head=(slot+1)&3;--wifi_data_count;return 0;}
    unsigned group=packet[16]&1;
    unsigned *credit=group?&wifi_tc5_free:&wifi_tc1_free;
    if(data_credit(*credit))return -1;
    if(!*credit)return 0; /* retain the request, retry without blocking management RX */
    wifi_data_head=(slot+1)&3;--wifi_data_count;
    unsigned ethernet_length=length<60?60:length;
    for(unsigned i=16+length;i<16+ethernet_length;i++)packet[i]=0;
    unsigned logical=16+ethernet_length,padded=(logical+3)&~3U;
    if(padded>512)padded=(padded+511)&~511U;
    for(unsigned i=logical;i<padded;i++)packet[i]=0;
    for(unsigned i=0;i<16;i++)packet[i]=0;
    packet[0]=logical;packet[1]=logical>>8;packet[2]=14;
    packet[3]=(group?5:1)<<2;packet[4]=14;packet[5]=0x10;
    packet[10]=group?0xff:0;packet[11]=0x20;
    if(wifi_timing_enabled && !group)wifi_tx_timing_other(&wifi_timing);
    if(!group)bench_credit_other();
    --*credit;
    if(extended_write(0x28,packet,padded,0)){wifi_tx_fault=1;return -1;}
    ++wifi_data_tx;
    if(wifi_verbose){field("WIFI Ethernet TX length=",length);field(" TC=",group?5:1);uart_puts("\n");}
    return 0;
}
void sdio_wifi_poll(void){
    wifi_credit_fresh=0;
    if(!wifi_ap_active)return;
    static uint8_t received[4096];unsigned length;
    if(event_read(received,sizeof received,&length)<0){
        wifi_ap_active=0;uart_puts("WIFI AP RX stopped on error\n");
    }
    if(!wifi_ap_active)return;
    if(wifi_management_pending){
        if(!wifi_management_done){
            if((TickType_t)(xTaskGetTickCount()-wifi_management_start)<1000)return;
            uart_puts("WIFI management TX done timeout\n");
            wifi_management_result=255;
        }
        unsigned kind=wifi_management_pending;
        wifi_management_pending=wifi_management_done=0;
        if(kind==0xb0){
            wifi_peer_state=wifi_management_result?1:2;
            field("WIFI peer authentication state=",wifi_peer_state);uart_puts("\n");
        }else if(kind==0x10 && !wifi_management_result){
            wifi_peer_state=3;wifi_peer_activate_pending=1;wifi_peer_activated=0;
            wifi_peer_activate_start=xTaskGetTickCount();
            if(station_update(3,1))goto failed;
            wifi_ap_bss[9]=0;
            if(control_set(0x16,wifi_ap_bss,sizeof wifi_ap_bss))goto failed;
        }
    }
    if(wifi_peer_activated && !wifi_peer_active){
        wifi_peer_active=1;uart_puts("WIFI peer associated AID=1 station_index=0 active\n");
    }
    if(wifi_peer_activate_pending &&
       (TickType_t)(xTaskGetTickCount()-wifi_peer_activate_start)>=3000){
        uart_puts("WIFI station activation timeout\n");goto failed;
    }
    if(!wifi_management_length){if(data_reply())goto failed;return;}
    /* Dispatch outside event_read: command waits may themselves drain RX. */
    uint8_t response[256]={0};
    unsigned subtype=wifi_management[0],frame;
    if(subtype==0){
        if(wifi_peer_state<2 || wifi_peer_activate_pending){wifi_management_length=0;return;}
        frame=wifi_assoc_reply_profile(wifi_management,wifi_management_length,wifi_mac,wifi_peer,
            ++wifi_management_sequence,response+16,sizeof response-16,&wifi_peer_rates,&wifi_peer_listen,wifi_rate_profile);
        if(frame && wifi_ht_enabled){
            if(!wifi_ht_parse(wifi_management+28,wifi_management_length-28,&wifi_peer_ht))frame=0;
            else if(wifi_peer_ht.qos){
                unsigned extra=wifi_ht_ies(response+16+frame,sizeof response-16-frame,wifi_ap_channel,wifi_ht_active(&wifi_peer_ht)!=0,1);
                if(!extra)frame=0;else frame+=extra;
            }
            field("WIFI peer HT present=",wifi_peer_ht.present);field(" qos=",wifi_peer_ht.qos);
            field(" MCS=",wifi_peer_ht.mcs);field(" active=",wifi_ht_active(&wifi_peer_ht));uart_puts("\n");
        }
    }else{
        frame=wifi_mgmt_reply_channel(wifi_management,wifi_management_length,
            wifi_mac,++wifi_management_sequence,response+16,sizeof response-16,wifi_rate_profile,wifi_ap_channel);
        if(frame && subtype==0x40 && wifi_ht_enabled){
            unsigned extra=wifi_ht_ies(response+16+frame,sizeof response-16-frame,wifi_ap_channel,1,1);
            if(!extra)frame=0;else frame+=extra;
        }
    }
    wifi_management_length=0;
    if(!frame)return;
    if(subtype==0 && wifi_fixed54 && !(wifi_peer_rates&0x2000)){
        uart_puts("WIFI association refused: peer lacks 54 Mbps\n");return;
    }
    if(subtype==0 || subtype==0xb0)wifi_peer_rcpi=wifi_management_rcpi;
    if(subtype==0xb0){
        if(wifi_peer_state){
            for(unsigned i=0;i<6;i++)if(wifi_management[10+i]!=wifi_peer[i])return;
        }
        for(unsigned i=0;i<6;i++)wifi_peer[i]=wifi_management[10+i];
        wifi_peer_state=1;wifi_peer_active=wifi_peer_activated=wifi_peer_activate_pending=0;
        wifi_peer_ht=(struct wifi_ht_peer){0};
        wifi_data_head=wifi_data_count=0;
        wifi_peer_rates=wifi_rates_get(wifi_rate_profile)->operational;wifi_peer_listen=1;
        if(station_update(1,0))goto failed;
    }
    unsigned logical=16+frame,padded=(logical+3)&~3U;
    response[0]=logical;response[1]=logical>>8;response[2]=20;response[3]=0xd0;
    response[4]=24;response[5]=0x90;response[10]=subtype==0x40?0xfe:0;response[11]=0x20;
    wifi_management_tx_sequence=(wifi_management_tx_sequence+1)&127U;
    if(!wifi_management_tx_sequence)++wifi_management_tx_sequence;
    response[12]=wifi_management_tx_sequence;response[13]=5;
    if(tc4_wait())goto failed;
    wifi_management_pending=response[16];wifi_management_done=0;
    wifi_management_pending_sequence=response[12];wifi_management_start=xTaskGetTickCount();
    if(tc4_write(response,padded))goto failed;
    field("WIFI management TX subtype=",response[16]);
    field(" sequence=",response[12]);uart_puts("\n");return;
failed:
    wifi_ap_active=0;uart_puts("WIFI management TX stopped on error\n");
}
/* Direct finite UDP diagnostic, independent of tuner/TS coordinator. */
static void bench_finish(const char *status){
    if(!wifi_bench_active)return;
    wifi_bench_active=0;
    wifi_io_stop(&wifi_bench_io,board_time_counts());
    field("WIFI TX bench packets=",wifi_bench_sent);
    field(" payload_bytes=",wifi_bench_sent*wifi_bench_size);
    field(" elapsed_ticks=",xTaskGetTickCount()-wifi_bench_begin);
    field(" stalls=",wifi_bench_stalls);field(" failed=",wifi_bench_failed);
    uart_puts("\n");
    field("WIFI TX bench timing counts=",wifi_bench_io.duration);
    field(" counts_per_tick=",(unsigned)R16(0xfffec006)+1U);
    field(" credit_pending=",wifi_bench_credit_pending);
    field(" credit_excluded=",wifi_bench_credit_excluded);uart_puts("\n");
    for(unsigned kind=0;kind<2;kind++){
        const struct wifi_io_bin *b=&wifi_bench_io.bin[kind];
        field("WIFI TX bench timing kind=",kind);field(" calls=",b->calls);field(" sum=",b->ticks);
        field(" min=",b->calls?b->minimum:0);field(" max=",b->maximum);
        field(" failed=",b->failed);field(" overflow=",b->overflow);uart_puts("\n");
    }
    uart_puts("WIFI TX bench end status=");uart_puts(status);uart_puts("\n");
}
void sdio_wifi_tx_bench_stop(void){bench_finish("interrupted");}
void sdio_wifi_tx_bench_size(void){
    static const unsigned sizes[]={64,256,512,1024,1332,1472};
    if(wifi_bench_active || wifi_sink_active || tuner_ts_stream_active()){
        uart_puts("WIFI TX bench size status=refused-active\n");return;
    }
    for(unsigned i=0;i<sizeof sizes/sizeof sizes[0];i++){
        if(wifi_bench_size==sizes[i]){
            wifi_bench_size=sizes[(i+1)%(sizeof sizes/sizeof sizes[0])];break;
        }
    }
    field("WIFI TX bench size payload_bytes=",wifi_bench_size);uart_puts("\n");
}
void sdio_wifi_tx_bench_burst(void){
    if(wifi_bench_active || wifi_sink_active || tuner_ts_stream_active()){
        uart_puts("WIFI TX bench burst status=refused-active\n");return;
    }
    wifi_bench_burst=wifi_bench_burst==1?4:wifi_bench_burst==4?8:1;
    field("WIFI TX bench burst packets=",wifi_bench_burst);uart_puts("\n");
}
void sdio_wifi_tx_bench_start(void){
    if(wifi_bench_active || !wifi_ap_active || !wifi_peer_activated || wifi_tx_fault ||
       wifi_sink_active || tuner_ts_stream_active() || sdio_wifi_raw_tx_selected()){
        uart_puts("WIFI TX bench begin status=refused-state\n");return;
    }
    wifi_bench_sent=wifi_bench_stalls=wifi_bench_failed=0;
    wifi_bench_credit_pending=wifi_bench_credit_excluded=0;
    wifi_io_start(&wifi_bench_io,board_time_counts());
    for(unsigned i=12;i<wifi_bench_size;i++)wifi_bench_body[i]=i%251;
    wifi_bench_body[0]='T';wifi_bench_body[1]='W';wifi_bench_body[2]='T';wifi_bench_body[3]='1';
    for(unsigned i=0;i<4;i++)wifi_bench_body[8+i]=wifi_bench_size>>(24-i*8);
    wifi_bench_begin=xTaskGetTickCount();wifi_bench_active=1;
    uart_puts("WIFI TX bench begin status=active\n");
}
static void bench_poll_one(void){
    static uint8_t packet[1536];
    if(!wifi_bench_active)return;
    if((uint32_t)(xTaskGetTickCount()-wifi_bench_begin)>=10000U || wifi_bench_sent>=20000U){
        bench_finish("complete");return;
    }
    if(!wifi_ap_active || !wifi_peer_activated || wifi_tx_fault || data_credit(wifi_tc1_free)){
        wifi_bench_failed=1;bench_finish("failed");return;
    }
    if(!ts_window_slots()){++wifi_bench_stalls;return;}
    for(unsigned i=0;i<4;i++)wifi_bench_body[4+i]=wifi_bench_sent>>(24-i*8);
    unsigned length=wifi_net_udp(wifi_bench_body,wifi_bench_size,4204,wifi_mac,wifi_peer,packet+16,sizeof packet-16);
    if(!length){wifi_bench_failed=1;bench_finish("failed");return;}
    unsigned logical=16+length;
    for(unsigned i=0;i<16;i++)packet[i]=0;
    packet[0]=logical;packet[1]=logical>>8;packet[2]=14;packet[3]=4;
    packet[4]=14;packet[5]=0x10;packet[11]=0x20;
    for(unsigned i=logical;i<sizeof packet;i++)packet[i]=0;
    uint32_t write_begin=board_time_counts();
    if(wifi_ts_window==1 && wifi_tc1_free==14){
        wifi_bench_credit_begin=write_begin;wifi_bench_credit_pending=1;
    }
    --wifi_tc1_free;
    int write_result=extended_write(0x28,packet,sizeof packet,0);
    wifi_io_record(&wifi_bench_io,0,sizeof packet,write_begin,board_time_counts(),write_result!=0);
    if(write_result){
        bench_credit_other();
        wifi_tx_fault=1;wifi_bench_failed=1;bench_finish("failed");return;
    }
    ++wifi_bench_sent;++wifi_data_tx;
}
void sdio_wifi_tx_bench_poll(void){
    uint32_t begin=xTaskGetTickCount();
    for(unsigned i=0;i<wifi_bench_burst && wifi_bench_active;i++){
        unsigned before=wifi_bench_sent;
        bench_poll_one();
        /* Return to UART/USB/RX service on no progress or after 4ms.
         * Each frame still reserves its own validated TC1 resource. */
        if(wifi_bench_sent==before || (uint32_t)(xTaskGetTickCount()-begin)>=4U)break;
    }
}
void sdio_wifi_more_data(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending || tuner_ts_stream_active() || sdio_wifi_raw_tx_selected()){
        uart_puts("WIFI more data end status=refused-active\n");return;
    }
    wifi_more_data^=1;field("WIFI more data selected=",wifi_more_data);
    uart_puts("\nWIFI more data end status=selected\n");
}
void sdio_wifi_rx_sink_stats(void){
    field("WIFI RX sink active=",wifi_sink_active);
    field(" packets=",wifi_sink.packets);field(" bytes=",wifi_sink.bytes);
    field(" missing=",wifi_sink.missing);field(" reordered=",wifi_sink.reordered);
    field(" invalid=",wifi_sink.invalid);field(" next_sequence=",wifi_sink.next_sequence);
    field(" first_tick=",wifi_sink.first_tick);field(" last_tick=",wifi_sink.last_tick);
    field(" max_gap_ticks=",wifi_sink.max_gap_ticks);field(" overflow=",wifi_sink.overflow);
    uint32_t end=wifi_sink_active?xTaskGetTickCount():wifi_sink_end;
    field(" window_ticks=",end-wifi_sink_begin);uart_puts("\n");
    uart_puts("WIFI RX sink stats end status=read\n");
}
void sdio_wifi_rx_sink_start(void){
    if(!wifi_ap_active || !wifi_peer_activated || wifi_tx_fault || tuner_ts_stream_active() || wifi_sink_active){
        uart_puts("WIFI RX sink start end status=refused-state\n");return;
    }
    wifi_sink=(struct wifi_rx_sink){0};wifi_sink_begin=xTaskGetTickCount();
    wifi_sink_end=wifi_sink_begin;wifi_sink_active=1;
    uart_puts("WIFI RX sink start end status=started\n");
}
void sdio_wifi_rx_sink_stop(void){
    if(wifi_sink_active){wifi_sink_end=xTaskGetTickCount();wifi_sink_active=0;}
    sdio_wifi_rx_sink_stats();uart_puts("WIFI RX sink stop end status=stopped\n");
}
void sdio_wifi_stats(void){
    field("WIFI raw TX selected=",wifi_raw_tx_mode);field(" qos_TC=",wifi_qos_tc);field(" fixed_MCS=",wifi_fixed_mcs);field(" more_data=",wifi_more_data);uart_puts("\n");
    field("WIFI IO enabled=",wifi_io_enabled);field(" active=",wifi_io.active);field(" counts=",wifi_io.duration);field(" counts_per_tick=",(unsigned)R16(0xfffec006)+1U);field(" nominal_hz=",BOARD_PCLK_HZ/8);
    field(" yields=",wifi_io_yields);field(" irq_waits=",wifi_io_irq_waits);field(" irq_ready=",wifi_io_irq_ready);uart_puts("\n");
    for(unsigned kind=0;kind<WIFI_IO_KINDS;kind++){
        const struct wifi_io_bin *b=&wifi_io.bin[kind];
        field("WIFI IO kind=",kind);field(" calls=",b->calls);field(" sum=",b->ticks);
        field(" min=",b->calls?b->minimum:0);field(" max=",b->maximum);field(" requested_bytes=",b->requested_bytes);
        field(" failed=",b->failed);field(" overflow=",b->overflow);uart_puts("\n");
    }

    field("WIFI SERVICE active=",wifi_service.phases.active);field(" counts=",wifi_service.phases.duration);field(" invalid=",wifi_service.invalid);uart_puts("\n");
    for(unsigned kind=0;kind<5;kind++){
        const struct wifi_io_bin *b=&wifi_service.phases.bin[kind];
        field("WIFI SERVICE phase=",kind);field(" calls=",b->calls);field(" sum=",b->ticks);
        field(" min=",b->calls?b->minimum:0);field(" max=",b->maximum);field(" overflow=",b->overflow);uart_puts("\n");
    }
    for(unsigned kind=0;kind<4;kind++){
        const struct wifi_io_bin *b=&wifi_service.loops.bin[kind];
        field("WIFI SERVICE class=",kind);field(" calls=",b->calls);field(" sum=",b->ticks);
        field(" min=",b->calls?b->minimum:0);field(" max=",b->maximum);
        field(" datagrams=",b->requested_bytes);field(" overflow=",b->overflow);uart_puts("\n");
    }
    field("WIFI power known=",wifi_power.known);
    field(" bss_events=",wifi_power.bss_events);field(" ps_events=",wifi_power.ps_events);
    field(" quota_events=",wifi_power.quota_events);field(" foreign=",wifi_power.foreign);
    field(" invalid=",wifi_power.invalid);field(" absent_raw=",wifi_power.absent);
    field(" bss_quota_raw=",wifi_power.bss_quota);field(" in_ps_raw=",wifi_power.in_ps);
    field(" ps_mode_raw=",wifi_power.ps_mode);field(" ps_quota_raw=",wifi_power.ps_quota);
    field(" quota_mode_raw=",wifi_power.quota_mode);field(" quota_raw=",wifi_power.quota);
    uart_puts("\n");
    field("WIFI stats RX=",wifi_data_rx);field(" TX=",wifi_data_tx);
    field(" queue_dropped=",wifi_data_dropped);field(" queued=",wifi_data_count);
    field(" TC1_free=",wifi_tc1_free);field(" TC2_free=",wifi_tc2_free);field(" TC3_free=",wifi_tc3_free);field(" TC4_free=",wifi_tc4_free);field(" TC5_free=",wifi_tc5_free);
    field(" peer_RCPI=",wifi_peer_rcpi);field(" fault=",wifi_tx_fault);
    field(" clock=",S(0x24));field(" read_mode=",wifi_read_fast);
    field(" write_mode=",wifi_write_fast);
    field(" irq=",sdio_irq_counter(0));field(" irq_hits=",sdio_irq_counter(1));
    field(" irq_waits=",sdio_irq_counter(2));field(" irq_ready=",sdio_irq_counter(3));
    field(" irq_timeouts=",sdio_irq_counter(4));field(" irq_spurious=",sdio_irq_counter(5));
    field(" tx_window=",wifi_ts_window);field(" window_stalls=",wifi_window_stalls);
    field(" queue_mode=",wifi_queue_mode);
    field(" poll_budget=",wifi_poll_budget);field(" wait_spins=",wifi_wait_spins);
    field(" wait_yields=",wifi_wait_yields);
    field(" poll_reuse=",wifi_poll_reuse);field(" tx_polls=",wifi_poll_count);
    field(" HT=",wifi_ht_enabled);field(" peer_HT=",wifi_ht_active(&wifi_peer_ht));
    field(" DPD_attempted=",wifi_dpd_attempted);field(" DPD_transferred=",wifi_dpd_transferred);
    field(" PER_attempted=",wifi_per_attempted);field(" PER_transferred=",wifi_per_transferred);field(" PER_steps=",wifi_per_steps);
    field(" credit_probe=",wifi_credit_probe);field(" probe_reads=",wifi_probe_reads);
    field(" scan_unresolved=",wifi_scan_unresolved);
    field(" ais_unresolved=",wifi_connection_unresolved);
    field(" ais_CAM_attempted=",wifi_ais_cam_attempted);field(" ais_CAM_transferred=",wifi_ais_cam_transferred);
    field(" probe_released=",wifi_probe_released);
    field(" status_poll=",wifi_status_polling);field(" status_reads=",wifi_status_reads);
    field(" reused=",wifi_reuse_count);
    field(" idle_deferred=",wifi_idle_deferred);field(" idle_polls=",wifi_idle_polls);
    field(" INFO2=",S(0x1e));uart_puts("\n");
    field("WIFI TS feedback enabled=",wifi_feedback_enabled);
    field(" requested=",wifi_feedback.requested);field(" completed=",wifi_feedback.completed);
    field(" pending=",wifi_feedback.pending);field(" skipped=",wifi_feedback.skipped);
    field(" unmatched=",wifi_feedback.unmatched);field(" cancelled=",wifi_feedback.cancelled);
    for(unsigned n=0;n<6;n++){field(" status=",n);field(" count=",wifi_feedback.status[n]);}
    unsigned known=0;for(unsigned n=0;n<6;n++)known+=wifi_feedback.status[n];
    field(" other=",wifi_feedback.completed-known);uart_puts("\n");
    field("WIFI TS timing enabled=",wifi_timing_enabled);field(" excluded=",wifi_timing.excluded);
    field(" pending_credit=",wifi_timing.active);uart_puts("\n");
    for(unsigned n=0;n<7;n++){
        struct wifi_tx_time_bin *b=wifi_timing.bin+n;
        if(!b->writes && !b->done && !b->credits)continue;
        field("WIFI TS latency packets=",n+1);field(" credits=",b->credits);
        field(" credit_sum=",b->credit_sum);field(" credit_min=",b->credit_min);field(" credit_max=",b->credit_max);
        field(" writes=",b->writes);field(" write_sum=",b->write_sum);field(" done=",b->done);
        field(" done_sum=",b->done_sum);field(" done_min=",b->done_min);field(" done_max=",b->done_max);
        field(" done_failed=",b->done_failed);
        field(" poll_sum=",b->poll_sum);field(" poll_min=",b->poll_min);field(" poll_max=",b->poll_max);
        field(" poll_gap_max=",b->poll_gap_max);uart_puts("\n");
    }
}
void sdio_wifi_tx_timing(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){uart_puts("WIFI TX timing end status=refused-active\n");return;}
    if(!wifi_hif_ready || wifi_tx_fault || wifi_tc1_free!=14 || wifi_tc4_free!=4 ||
       wifi_tc5_free!=1 || wifi_feedback.pending){uart_puts("WIFI TX timing end status=refused-state\n");return;}
    wifi_timing_enabled^=1;wifi_tx_timing_reset(&wifi_timing);
    field("WIFI TX timing selected=",wifi_timing_enabled);uart_puts("\nWIFI TX timing end status=selected\n");
}
void sdio_wifi_ts_feedback(void){
    wifi_feedback_enabled=!wifi_feedback_enabled;
    field("WIFI TS feedback enabled=",wifi_feedback_enabled);uart_puts("\n");
}
void sdio_wifi_poll_reuse(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI poll reuse end status=refused-active\n");return;
    }
    wifi_poll_reuse^=1;wifi_credit_fresh=0;
    wifi_poll_count=wifi_reuse_count=0;
    field("WIFI poll reuse selected=",wifi_poll_reuse);uart_puts("\n");
    uart_puts("WIFI poll reuse end status=selected\n");
}
void sdio_wifi_credit_probe(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI credit probe end status=refused-active\n");return;
    }
    if(!wifi_hif_ready || wifi_tx_fault || wifi_status_polling || tx_poll() ||
       wifi_tc1_free!=14 || wifi_tc2_free!=1 || wifi_tc3_free!=1 ||
       wifi_tc4_free!=4 || wifi_tc5_free!=1){
        uart_puts("WIFI credit probe end status=refused-state\n");return;
    }
    wifi_credit_probe^=1;wifi_probe_reads=wifi_probe_released=0;wifi_credit_fresh=0;
    field("WIFI credit probe selected=",wifi_credit_probe);
    uart_puts("\nWIFI credit probe end status=selected\n");
}
void sdio_wifi_status_poll(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI status poll end status=refused-active\n");return;
    }
    uint32_t control;
    if(!wifi_hif_ready || wifi_tx_fault || wifi_credit_probe || radio_read(0x0c,&control) ||
       (control&0x100f2UL)!=0x10 || tx_poll() ||
       wifi_tc1_free!=14 || wifi_tc4_free!=4 || wifi_tc5_free!=1){
        uart_puts("WIFI status poll end status=refused-state\n");return;
    }
    /* Keep MAX_RX=1 and RX-payload enhancement disabled. Only the fixed
     * interrupt/status port read changes; no new appended RX format. */
    wifi_status_polling^=1;wifi_status_rx=0;wifi_credit_fresh=0;
    field("WIFI status poll selected=",wifi_status_polling);uart_puts("\n");
    uart_puts("WIFI status poll end status=selected\n");
}
void sdio_wifi_queue(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI queues end status=refused-active\n");return;
    }
    wifi_queue_mode=(wifi_queue_mode+1)%3;
    field("WIFI queues selected=",wifi_queue_mode);uart_puts("\n");
    uart_puts("WIFI queues end status=selected\n");
}
void sdio_wifi_tx_window(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI TX window end status=refused-active\n");return;
    }
    if(!wifi_hif_ready || wifi_tx_fault || tx_poll() ||
       wifi_tc1_free!=14 || wifi_tc4_free!=4 || wifi_tc5_free!=1){
        uart_puts("WIFI TX window end status=refused-state\n");return;
    }
    wifi_ts_window=wifi_ts_window==14?1:wifi_ts_window==1?4:14;
    wifi_window_stalls=0;
    field("WIFI TX window selected=",wifi_ts_window);uart_puts("\n");
    uart_puts("WIFI TX window end status=selected\n");
}
void sdio_wifi_irq(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI IRQ end status=refused-active\n");return;
    }
    if(!sdio_irq_enabled() && (!card_verified || !wifi_hif_ready || wifi_tx_fault ||
        tx_poll() || wifi_tc1_free!=14 || wifi_tc4_free!=4 || wifi_tc5_free!=1)){
        uart_puts("WIFI IRQ end status=refused-state\n");return;
    }
    if(sdio_irq_set(!sdio_irq_enabled())){
        uart_puts("WIFI IRQ end status=refused-state\n");return;
    }
    field("WIFI IRQ selected=",sdio_irq_enabled());uart_puts("\n");
    uart_puts("WIFI IRQ end status=selected\n");
}
void sdio_wifi_poll_budget(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending){
        uart_puts("WIFI poll budget end status=refused-active\n");return;
    }
    wifi_poll_budget=wifi_poll_budget==64?4096:64;
    wifi_wait_spins=wifi_wait_yields=0;
    field("WIFI poll budget selected=",wifi_poll_budget);uart_puts("\n");
    uart_puts("WIFI poll budget end status=selected\n");
}
void sdio_wifi_read_polling(void){
    wifi_read_fast=(wifi_read_fast+1)%5;
    field("WIFI read polling=",wifi_read_fast);uart_puts("\n");
}
void sdio_wifi_write_polling(void){
    wifi_write_fast=(wifi_write_fast+1)%4;
    field("WIFI write polling=",wifi_write_fast);uart_puts("\n");
}
void sdio_wifi_verbose(void){
    wifi_verbose=!wifi_verbose;field("WIFI verbose=",wifi_verbose);uart_puts("\n");
}
void sdio_wifi_read_check(void){
    uart_puts("WIFI read check start\n");
    unsigned previous=wifi_read_fast;int result=-1;
    if(!card_verified){uart_puts("WIFI read check card not verified\n");goto done;}
    for(unsigned mode=0;mode<5;mode++){
        wifi_read_fast=mode;unsigned count=0,mismatches=0,byte_checks=0;
        uint32_t chip=0;TickType_t start=xTaskGetTickCount();
        for(;count<1024;count++){
            if(radio_read(0,&chip))goto done;
            if((chip&0xffff)!=0x5931)mismatches++;
            if(!(count&15)){
                uint8_t low,high;
                if(direct(1,0,&low,0) || direct(1,1,&high,0))goto done;
                byte_checks++;
                if(low!=0x31 || high!=0x59)mismatches++;
            }
            if((TickType_t)(xTaskGetTickCount()-start)>=10000){
                uart_puts("WIFI read check deadline\n");goto done;
            }
        }
        field("WIFI read check mode=",mode);field(" words=",count);
        field(" byte_pairs=",byte_checks);field(" mismatches=",mismatches);
        field(" ticks=",(TickType_t)(xTaskGetTickCount()-start));field(" last_WCIR=",chip);uart_puts("\n");
        if(mismatches)goto done;
    }
    result=0;
done:
    wifi_read_fast=previous;field("WIFI read check restored_mode=",wifi_read_fast);uart_puts("\n");
    uart_puts(result?"WIFI read check end status=failed\n":"WIFI read check end status=ready\n");
}
void sdio_wifi_clock(void){
    uart_puts("WIFI normal clock start\n");
    uint8_t capability;uint16_t previous=S(0x24);uint32_t chip;
    /* Stock SH2A18054e0e..1b checks CCCR08 bit6 (low-speed card), then
     * writes0101 to the same controller. Retain our proven one-bit bus.
     * This changes the SD bus divider, not the radio's RF channel/rate. */
    if(!card_verified || !(previous&0x100) || read_byte(8,&capability))goto failed;
    field("WIFI card capability=",capability);uart_puts("\n");
    if(capability&0x40){uart_puts("WIFI low-speed card; clock unchanged\n");goto failed;}
    S(0x24)=previous&~0x100;vTaskDelay(1);
    S(0x24)=1;S(0x24)=0x101;vTaskDelay(1);
    if(S(0x24)==0x101 && !radio_read(0,&chip) && (chip&0xffff)==0x5931){
        field("WIFI normal clock verified register=",S(0x24));field(" WCIR=",chip);uart_puts("\n");
        uart_puts("WIFI normal clock end status=ready\n");return;
    }
    S(0x24)&=~0x100;S(0x24)=previous&~0x100;S(0x24)=previous;vTaskDelay(1);
    uart_puts("WIFI normal clock probe failed; previous divider restored\n");
failed:
    uart_puts("WIFI normal clock end status=failed\n");
}
void sdio_wifi_width(void){
    uint8_t previous,capability,value;uint32_t chip,current;
    uint16_t option=S(0x28);unsigned count=0,pairs=0;
    uart_puts("WIFI width start\n");
    if(!card_verified || wifi_tx_fault || read_byte(7,&previous) ||
       read_byte(8,&capability) || radio_read(0,&chip) || (chip&0xffff)!=0x5931)goto failed;
    field("WIFI width before_CCCR07=",previous);field(" capability=",capability);
    field(" OPTION=",option);field(" WCIR=",chip);uart_puts("\n");
    unsigned old_width=previous&3;
    if((old_width!=0 && old_width!=2) || (!!(option&0x8000)!=(old_width==0))){
        uart_puts("WIFI width inconsistent state; unchanged\n");goto failed;
    }
    if(old_width==0 && (capability&0x40) && !(capability&0x80)){
        uart_puts("WIFI width unsupported low-speed card; unchanged\n");goto failed;
    }
    uint8_t selected=(previous&~3U)|(old_width==0?2:0);
    /* CMD52 travels on CMD independently of DAT width. Preserve unrelated
     * CCCR07/OPTION fields; the stock SH2A18054e34..56 path sets CCCR07=2
     * then clears OPTION bit15. No register names beyond that evidence. */
    value=selected;
    if(direct(0,7,&value,1) || read_byte(7,&value) || value!=selected)goto restore;
    uint16_t selected_option=old_width==0?option&~0x8000U:option|0x8000U;
    S(0x28)=selected_option;
    if(S(0x28)!=selected_option)goto restore;
    for(;count<128;count++){
        if(radio_read(0,&current) || current!=chip)goto restore;
        if(!(count&15)){
            uint8_t low,high;
            if(direct(1,0,&low,0) || direct(1,1,&high,0) || low!=0x31 || high!=0x59)goto restore;
            pairs++;
        }
    }
    field("WIFI width selected=",old_width==0?4:1);field(" CCCR07=",value);
    field(" OPTION=",S(0x28));field(" words=",count);field(" byte_pairs=",pairs);uart_puts("\n");
    uart_puts("WIFI width end status=verified-reads\n");return;
restore:
    field("WIFI width probe failed words=",count);field(" byte_pairs=",pairs);status();
    value=previous;int bad=direct(0,7,&value,1);
    S(0x28)=option;(void)S(0x28);
    if(read_byte(7,&value) || value!=previous || S(0x28)!=option ||
       radio_read(0,&current) || current!=chip)bad=1;
    field("WIFI width restored=",!bad);field(" OPTION=",S(0x28));uart_puts("\n");
    if(bad)wifi_tx_fault=1;
failed:
    uart_puts("WIFI width end status=failed\n");
}


void sdio_wifi_io_start(void){
    if(!wifi_io_enabled)return;
    wifi_io_yields_begin=wifi_wait_yields;
    wifi_io_irq_begin=sdio_irq_counter(2);wifi_io_ready_begin=sdio_irq_counter(3);
    wifi_io_yields=wifi_io_irq_waits=wifi_io_irq_ready=0;
    uint32_t now=board_time_counts();
    wifi_io_start(&wifi_io,now);wifi_service_start(&wifi_service,now);
}
void sdio_wifi_service_mark(unsigned mark){
    if(wifi_service.phases.active)wifi_service_mark(&wifi_service,mark,board_time_counts(),wifi_window_stalls,wifi_data_tx);
}
void sdio_wifi_io_timing(void){
    uart_puts("WIFI IO timing start\n");
    if(tuner_ts_stream_active()){uart_puts("WIFI IO timing end status=refused-active\n");return;}
    wifi_io_enabled^=1;
    field("WIFI IO timing selected=",wifi_io_enabled);uart_puts("\nWIFI IO timing end status=selected\n");
}

unsigned sdio_wifi_raw_tx_selected(void){return wifi_raw_tx_mode;}
unsigned sdio_wifi_qos_class_selected(void){return wifi_qos_tc;}
void sdio_wifi_raw_tx(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending || tuner_ts_stream_active()){
        uart_puts("WIFI raw TX end status=refused-active\n");return;
    }
    if(tuner_ts_stream_aggregate_active()){
        uart_puts("WIFI raw TX end status=refused-aggregate\n");return;
    }
    wifi_raw_tx_mode=wifi_raw_tx_mode?0:1;wifi_qos_tc=1;
    field("WIFI raw TX selected=",wifi_raw_tx_mode);uart_puts("\nWIFI raw TX end status=selected\n");
}
void sdio_wifi_qos_tx(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending || tuner_ts_stream_active()){
        uart_puts("WIFI QoS TX end status=refused-active\n");return;
    }
    if(tuner_ts_stream_aggregate_active() || !wifi_raw_tx_mode){
        uart_puts("WIFI QoS TX end status=refused-raw-state\n");return;
    }
    if(wifi_raw_tx_mode!=2 && !wifi_ht_enabled){
        uart_puts("WIFI QoS TX end status=refused-ht\n");return;
    }
    wifi_raw_tx_mode=wifi_raw_tx_mode==2?1:2;
    field("WIFI raw TX selected=",wifi_raw_tx_mode);uart_puts("\nWIFI QoS TX end status=selected\n");
}
void sdio_wifi_qos_class(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending || tuner_ts_stream_active()){
        uart_puts("WIFI QoS class end status=refused-active\n");return;
    }
    if(wifi_raw_tx_mode!=2 || !wifi_ht_enabled || tuner_ts_stream_aggregate_active() || wifi_timing_enabled){
        uart_puts("WIFI QoS class end status=refused-mode\n");return;
    }
    if(!wifi_hif_ready || wifi_tx_fault || wifi_tc1_free!=14 || wifi_tc2_free!=1 || wifi_tc3_free!=1 || wifi_feedback.pending){
        uart_puts("WIFI QoS class end status=refused-credit\n");return;
    }
    wifi_qos_tc=wifi_qos_tc==1?2:wifi_qos_tc==2?3:1;
    field("WIFI QoS class selected=",wifi_qos_tc);uart_puts("\nWIFI QoS class end status=selected\n");
}
void sdio_wifi_fixed_mcs(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending || tuner_ts_stream_active()){
        uart_puts("WIFI fixed MCS end status=refused-active\n");return;
    }
    if(!wifi_ht_enabled || wifi_fixed54){uart_puts("WIFI fixed MCS end status=refused-profile\n");return;}
    wifi_fixed_mcs=(wifi_fixed_mcs+1)%3;
    field("WIFI fixed MCS selected=",wifi_fixed_mcs);uart_puts("\nWIFI fixed MCS end status=selected\n");
}
void sdio_wifi_ht(void){
    uart_puts("WIFI HT start\n");
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending || tuner_ts_stream_active()){
        uart_puts("WIFI HT end status=refused-active\n");return;
    }
    if(wifi_raw_tx_mode==2 || wifi_fixed_mcs){uart_puts("WIFI HT end status=refused-fixed-mode\n");return;}
    wifi_ht_enabled^=1;
    field("WIFI HT selected=",wifi_ht_enabled);uart_puts("\nWIFI HT end status=selected\n");
}

void sdio_wifi_channel(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending || tuner_ts_stream_active()){
        uart_puts("WIFI channel end status=refused-active\n");return;
    }
    if(!wifi_hif_ready || wifi_tx_fault || wifi_tc1_free!=14 || wifi_tc4_free!=4 ||
       wifi_tc5_free!=1 || wifi_feedback.pending){
        uart_puts("WIFI channel end status=refused-state\n");return;
    }
    unsigned next=wifi_channel_next(wifi_ap_channel);
    if(!next){uart_puts("WIFI channel end status=refused-state\n");return;}
    wifi_ap_channel=next;
    field("WIFI channel selected=",wifi_ap_channel);uart_puts("\nWIFI channel end status=selected\n");
}
void sdio_wifi_ts_timing_stop(void){
    if(wifi_io.active){
        uint32_t now=board_time_counts();
        wifi_service_stop(&wifi_service,now);wifi_io_stop(&wifi_io,now);
        wifi_io_yields=wifi_wait_yields-wifi_io_yields_begin;
        wifi_io_irq_waits=sdio_irq_counter(2)-wifi_io_irq_begin;
        wifi_io_irq_ready=sdio_irq_counter(3)-wifi_io_ready_begin;
    }

    if(wifi_timing_enabled)wifi_tx_timing_other(&wifi_timing);
}
void sdio_wifi_channel_bssid(void){
    if(wifi_ap_active || wifi_peer_state || wifi_peer_activate_pending || tuner_ts_stream_active()){
        uart_puts("WIFI channel BSSID end status=refused-active\n");return;
    }
    if(!wifi_hif_ready || wifi_tx_fault || wifi_tc1_free!=14 || wifi_tc4_free!=4 ||
       wifi_tc5_free!=1 || wifi_feedback.pending){
        uart_puts("WIFI channel BSSID end status=refused-state\n");return;
    }
    wifi_channel_bssid_mode^=1;
    field("WIFI channel BSSID selected=",wifi_channel_bssid_mode);uart_puts("\nWIFI channel BSSID end status=selected\n");
}
