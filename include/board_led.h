/* SPDX-License-Identifier: MIT */
#ifndef BOARD_LED_H
#define BOARD_LED_H
/* Two status LEDs, wired as in the stock firmware (static_batch/18054736.c, board strap
 * (PBDR0>>7)&7: 0 -> PC3/PC4, 1 -> PB12/PB13, 2 -> PE0/PE1). Active low: the stock init drives
 * both high (off) and a nonzero argument drives the pin low. Pin function (PFC) is set to GPIO
 * exactly as the stock does. */
enum {BOARD_LED_OFF=0,BOARD_LED_BUSY=1,BOARD_LED_READY=2,BOARD_LED_FAILED=3};
/* Configures the pins (idempotent). Returns the strap value, or -1 when no LED wiring is known. */
int board_led_init(void);
/* Drives one LED (0 or 1) now and stops the automatic pattern until board_led_auto(). */
void board_led_set(unsigned led,unsigned on);
void board_led_auto(void);
/* Pattern for a state: BUSY led1 solid; READY led0 solid (led1 blinks while streaming);
 * FAILED both blink fast; OFF dark. */
void board_led_state(unsigned state);
/* Call from the UART task loop. now is in ms ticks. */
void board_led_service(unsigned now,int streaming);
/* UART byte 10: argument byte bit0 = LED0, bit1 = LED1, 0xff = back to automatic. */
void board_led_command(void);
#endif
