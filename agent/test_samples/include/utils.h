#ifndef UTILS_H
#define UTILS_H

#include <stddef.h>

/* String utility functions */
char* copy_string(char* dest, char* src);
int safe_divide(int a, int b);
void* alloc_buffer(size_t size);
void free_buffer(void* buf);
int parse_int(const char* str);

#endif
