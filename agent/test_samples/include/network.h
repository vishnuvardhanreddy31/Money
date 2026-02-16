#ifndef NETWORK_H
#define NETWORK_H

#include <stddef.h>

/* Network operations */
int connect_to_server(const char* host, int port);
int send_data(int socket_fd, const char* data, size_t len);
int receive_data(int socket_fd, char* buffer, size_t buf_size);
void close_connection(int socket_fd);

/* Shared state for connection pool */
extern int connection_count;
extern int max_connections;

#endif
