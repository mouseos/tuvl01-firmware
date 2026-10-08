/* Independent freestanding SH-2A platform declarations. */
#ifndef TUVL_WPA_INCLUDES_H
#define TUVL_WPA_INCLUDES_H
#define INCLUDES_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>
#include <limits.h>
#define ENOMEM 12
#define __LITTLE_ENDIAN 1234
#define __BIG_ENDIAN 4321
#define __BYTE_ORDER __BIG_ENDIAN
#define bswap_16(x) __builtin_bswap16(x)
#define bswap_32(x) __builtin_bswap32(x)
#define bswap_64(x) __builtin_bswap64(x)
typedef long ssize_t;
typedef struct tuvl_wpa_unavailable_file FILE;
void free(void *ptr);
void *memset(void *ptr,int c,size_t n);
int isspace(int c);
int atoi(const char *s);
int abs(int value);
long strtol(const char *s,char **end,int base);
void qsort(void *base,size_t n,size_t size,int (*compare)(const void *,const void *));
int vsnprintf(char *buf,size_t n,const char *fmt,va_list ap);
void abort(void);
#endif
