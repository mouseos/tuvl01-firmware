/* SPDX-License-Identifier: MIT */
#ifndef TUNER_H
#define TUNER_H
#include <stdint.h>
void tuner_probe(void);
void tuner_board_probe(void);
void tuner_rf_switch(void);
void tuner_reg_access(void);
void tuner_program_port_probe(void);
void tuner_gpio_dump(void);
void tuner_gpio_drive(void);
void tuner_gpio_release(void);
int tuner_read_register(unsigned address,unsigned reg,uint8_t *byte);
int tuner_write_register(unsigned address,unsigned reg,uint8_t byte);
void tuner_analog(void);
void tuner_initialize(void);
#endif
