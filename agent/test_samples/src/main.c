#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "utils.h"
#include "network.h"

#define MAX_INPUT 1024
#define MAX_USERS 50

typedef struct {
    char name[64];
    int id;
    double balance;
} User;

User users[MAX_USERS];
int user_count = 0;

/* BUG: Format string vulnerability - user input passed directly to printf */
void print_user_info(const char* user_input) {
    printf(user_input);
    printf("\n");
}

/* BUG: Array index not validated - can write out of bounds */
void add_user(const char* name, int id, double balance) {
    strcpy(users[user_count].name, name);  /* BUG: No length check on name - buffer overflow */
    users[user_count].id = id;
    users[user_count].balance = balance;
    user_count++;
    /* BUG: No check if user_count >= MAX_USERS */
}

/* BUG: Double-free potential */
void process_data(const char* input) {
    char* buffer = (char*)malloc(strlen(input) + 1);
    if (!buffer) return;

    strcpy(buffer, input);

    /* Process ... */
    if (strlen(buffer) > 100) {
        free(buffer);
        /* Fall through - buffer freed but used below */
    }

    /* BUG: Use-after-free if buffer was freed above */
    printf("Processed: %s\n", buffer);
    free(buffer);  /* BUG: Double-free if buffer was freed in the if-block */
}

/* BUG: Memory leak - file handle not closed on error path */
int read_config(const char* filename) {
    FILE* fp = fopen(filename, "r");
    if (!fp) return -1;

    char line[256];
    while (fgets(line, sizeof(line), fp)) {
        if (strncmp(line, "ERROR", 5) == 0) {
            return -2;  /* BUG: fp not closed before return */
        }
    }

    fclose(fp);
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <config_file>\n", argv[0]);
        return 1;
    }

    /* BUG: No validation of argv[1] - possible path traversal */
    int result = read_config(argv[1]);

    char input[MAX_INPUT];
    printf("Enter data: ");
    /* BUG: gets() is dangerous - use fgets instead. Using scanf without width */
    scanf("%s", input);

    process_data(input);

    /* Cross-module interaction: using network + utils */
    int fd = connect_to_server("localhost", 8080);
    if (fd > 0) {
        char* msg = (char*)alloc_buffer(128);
        copy_string(msg, input);
        send_data(fd, msg, strlen(msg));
        free_buffer(msg);
        /* BUG: msg is dangling pointer after free_buffer, could be reused */
        close_connection(fd);
    }

    return 0;
}
