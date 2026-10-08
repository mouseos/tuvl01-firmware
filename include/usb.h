/* SPDX-License-Identifier: MIT */
#ifndef USB_H
#define USB_H
void usb_init(void);
void usb_poll(void);
void usb_detach(void);
unsigned usb_configured(void);
void usb_debug(void);
void usb_pin_debug(void);
/* Device vendor request hook: positive = IN bytes; 0 = status; -1 = STALL.
 * OUT data are accepted separately after validated SETUP. */
int usb_request(unsigned type,unsigned req,unsigned value,unsigned index,unsigned length,unsigned char *reply);
int usb_out(const unsigned char *data,unsigned length);
void usb_idle(void);
#endif
