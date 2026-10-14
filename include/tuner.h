/* SPDX-License-Identifier: MIT */
#ifndef TUNER_H
#define TUNER_H
#include <stdint.h>
void tuner_probe(void);
void tuner_board_probe(void);
void tuner_rf_switch(void);
void tuner_reg_access(void);
void tuner_program_port_probe(void);
void tuner_program_burst_probe(void);
void tuner_program_release_probe(void);
void tuner_program_restart_probe(void);
void tuner_program_address_probe(void);
void tuner_program_mailbox_probe(void);
void tuner_program_mailbox_sweep(void);
void tuner_program_mailbox_select(void);
int tuner_program_mailbox_operand(uint16_t operand);
void tuner_monitor_window_probe(void);
void tuner_monitor_window_updates(void);
void tuner_monitor_window_timing(void);
void tuner_d4_window_halted(void);
void tuner_d4_window_live_buffered(void);
void tuner_d4_window_live_selected(unsigned index);
void tuner_d4_window_live_select(void);
void tuner_d4_window_live_experimental(unsigned index);
void tuner_d4_window_experimental_select(void);
int tuner_program_mailbox_original_valid(void);
uint16_t tuner_program_mailbox_known_operand(unsigned index);
int tuner_program_mailbox_write_record(uint16_t operand,uint8_t *expected);
int tuner_program_mailbox_write_d5_record(uint8_t *expected,unsigned write20);
void tuner_program_mailbox_d5(void);
void tuner_program_mailbox_d5_write20(void);
void tuner_pin_capture_probe(void);
void tuner_pin_test_probe(void);
void tuner_pin_gpio_selftest(void);
void tuner_gpio_dump(void);
void tuner_gpio_drive(void);
void tuner_gpio_release(void);
int tuner_read_register(unsigned address,unsigned reg,uint8_t *byte);
/* Finite 1..8 byte transaction; received reports actual bytes on failure.
 * Register auto-increment and stream semantics belong to the target chip. */
int tuner_read_burst(unsigned address,unsigned reg,uint8_t *bytes,unsigned count,unsigned *received);
/* Same finite receive loop; repeated START instead of intermediate STOP.
 * Accepts 2..8 bytes, and leaves register/source selection unchanged. */
int tuner_read_burst_restart(unsigned address,unsigned reg,uint8_t *bytes,unsigned count,unsigned *received);
int tuner_write_register(unsigned address,unsigned reg,uint8_t byte);
/* One pointer write followed by 1..128 payload bytes in a single transaction. */
int tuner_write_burst(unsigned address,unsigned reg,const uint8_t *bytes,unsigned count);
void tuner_analog(void);
void tuner_initialize(void);
int tuner_program_mailbox_write_reference_record(unsigned index,uint8_t *expected);
int tuner_program_mailbox_reference(unsigned index);
void tuner_program_mailbox_reference_select(void);

#endif
