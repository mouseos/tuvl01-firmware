#ifndef TUVL_STRING_H
#define TUVL_STRING_H
#include <stddef.h>
void *memset(void *,int,size_t);
void *memcpy(void *,const void *,size_t);
int memcmp(const void *,const void *,size_t);
size_t strlen(const char *);
#endif
