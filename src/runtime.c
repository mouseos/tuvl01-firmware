/* SPDX-License-Identifier: MIT */
#include <stddef.h>
void *memset(void *d,int c,size_t n) { unsigned char *p=d; while(n--) *p++=(unsigned char)c; return d; }
void *memcpy(void *d,const void *s,size_t n) { unsigned char *p=d; const unsigned char *q=s; while(n--) *p++=*q++; return d; }
int memcmp(const void *a,const void *b,size_t n) { const unsigned char *p=a,*q=b; while(n--) { if(*p!=*q) return *p-*q; p++;q++; } return 0; }
size_t strlen(const char *s) { size_t n=0;while(s[n])n++;return n; }
