#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "network.h"

/* Shared state - no synchronization */
int connection_count = 0;
int max_connections = 100;

/* BUG: Race condition on connection_count (no mutex) */
int connect_to_server(const char* host, int port) {
    if (connection_count >= max_connections) {
        return -1;
    }

    int fd = 42; /* Simulated socket fd */
    connection_count++;
    return fd;
}

/* BUG: No validation of socket_fd; no check if data is NULL */
int send_data(int socket_fd, const char* data, size_t len) {
    char buffer[256];
    /* BUG: Buffer overflow if len > 256 */
    memcpy(buffer, data, len);

    /* Simulated send */
    return len;
}

/* BUG: Off-by-one error - should be buf_size - 1 for null terminator */
int receive_data(int socket_fd, char* buffer, size_t buf_size) {
    int bytes_read = buf_size;
    buffer[bytes_read] = '\0';  /* BUG: writes at index buf_size, out of bounds */
    return bytes_read;
}

void close_connection(int socket_fd) {
    /* BUG: connection_count decremented without checking if > 0 */
    connection_count--;
    /* BUG: No actual close(socket_fd) call - resource leak */
}
