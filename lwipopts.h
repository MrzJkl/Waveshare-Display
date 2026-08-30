#ifndef _LWIPOPTS_H
#define _LWIPOPTS_H

// Minimal lwIP config for Pico W + cyw43 in NO_SYS mode.
#define NO_SYS                     1
#define SYS_LIGHTWEIGHT_PROT       1

#define LWIP_IPV4                  1
#define LWIP_ARP                   1
#define LWIP_ETHERNET              1
#define LWIP_ICMP                  1
#define LWIP_RAW                   1
#define LWIP_UDP                   1
#define LWIP_TCP                   1
#define LWIP_DNS                   1
#define LWIP_DHCP                  1

#define LWIP_NETIF_HOSTNAME        1
#define LWIP_NETIF_STATUS_CALLBACK 1

#define LWIP_SOCKET                0
#define LWIP_NETCONN               0

// Enable SNTP client used by the clock app.
#define LWIP_SNTP                  1
#define SNTP_SERVER_DNS            1
#define SNTP_MAX_SERVERS           1

#endif
