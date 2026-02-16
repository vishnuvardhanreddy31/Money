#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "utils.h"

/* BUG: No bounds checking - buffer overflow possible */
char* copy_string(char* dest, char* src) {
    int i = 0;
    while (src[i] != '\0') {
        dest[i] = src[i];
        i++;
    }
    /* BUG: Missing null terminator */
    return dest;
}

/* BUG: Division by zero not handled */
int safe_divide(int a, int b) {
    return a / b;
}

void* alloc_buffer(size_t size) {
    void* buf = malloc(size);
    /* BUG: No NULL check after malloc */
    memset(buf, 0, size);
    return buf;
}

void free_buffer(void* buf) {
    free(buf);
    /* BUG: Not setting pointer to NULL after free (caller can use-after-free) */
}

/* BUG: Signed integer overflow for large values, atoi has no error handling */
int parse_int(const char* str) {
    int result = 0;
    int sign = 1;
    int i = 0;

    if (str[0] == '-') {
        sign = -1;
        i = 1;
    }

    while (str[i] != '\0') {
        result = result * 10 + (str[i] - '0');
        i++;
    }

    return sign * result;
}
