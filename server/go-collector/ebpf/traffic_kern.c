// traffic_kern.c — eBPF kernel program for per-IP traffic accounting
// Attaches to TC (traffic control) ingress/egress hooks.
// Requires: Linux kernel >= 5.4, clang + libbpf for compilation.

#include <linux/bpf.h>
#include <linux/pkt_cls.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/ipv6.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#define MAX_ENTRIES 65536
#define MAX_PORTS  16

// Per-packet event pushed to userspace via ring buffer
struct packet_event {
	__u64 timestamp_ns;
	__u32 ifindex;
	__u32 saddr;
	__u32 daddr;
	__u16 sport;
	__u16 dport;
	__u8  proto;   // 6=TCP, 17=UDP
	__u8  direction; // 0=ingress(rx), 1=egress(tx)
	__u32 size;
	__u32 pid;       // filled by userspace
};

// ring buffer for pushing events to userspace
struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, 256 * 1024); // 256KB ring buffer
} events SEC(".maps");

// Interface-index filter map (populated by userspace: which ifaces to monitor)
struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, 64);
	__type(key, __u32);
	__type(value, __u8);
} iface_filter SEC(".maps");

// Per-IP byte counter (userspace can read & aggregate)
struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_HASH);
	__uint(max_entries, MAX_ENTRIES);
	__type(key, __u32);   // IP address
	__type(value, __u64); // accumulated bytes
} ip_bytes SEC(".maps");

static __always_inline int is_private_ip(__u32 addr) {
	__u32 host = bpf_ntohl(addr);
	// 10.0.0.0/8
	if ((host & 0xFF000000) == 0x0A000000) return 1;
	// 172.16.0.0/12
	if ((host & 0xFFF00000) == 0xAC100000) return 1;
	// 192.168.0.0/16
	if ((host & 0xFFFF0000) == 0xC0A80000) return 1;
	// 127.0.0.0/8
	if ((host & 0xFF000000) == 0x7F000000) return 1;
	return 0;
}

SEC("tc_ingress")
int tc_ingress(struct __sk_buff *skb) {
	__u32 ifindex = skb->ifindex;
	__u8 *found = bpf_map_lookup_elem(&iface_filter, &ifindex);
	if (!found)
		return TC_ACT_UNSPEC;

	// Parse packet
	void *data = (void *)(long)skb->data;
	void *data_end = (void *)(long)skb->data_end;
	struct ethhdr *eth = data;
	if ((void *)(eth + 1) > data_end)
		return TC_ACT_UNSPEC;

	__u16 proto = eth->h_proto;
	if (proto != bpf_htons(ETH_P_IP))
		return TC_ACT_UNSPEC;

	struct iphdr *ip = (void *)(eth + 1);
	if ((void *)(ip + 1) > data_end)
		return TC_ACT_UNSPEC;

	__u32 size = skb->len;

	// Track per-IP bytes
	__u32 *bytes = bpf_map_lookup_elem(&ip_bytes, &ip->saddr);
	if (bytes) {
		__sync_fetch_and_add(bytes, size);
	}
	bytes = bpf_map_lookup_elem(&ip_bytes, &ip->daddr);
	if (bytes) {
		__sync_fetch_and_add(bytes, size);
	}

	// Build and submit event
	struct packet_event *evt = bpf_ringbuf_reserve(&events, sizeof(struct packet_event), 0);
	if (!evt)
		return TC_ACT_UNSPEC;

	evt->timestamp_ns = bpf_ktime_get_ns();
	evt->ifindex = ifindex;
	evt->saddr = ip->saddr;
	evt->daddr = ip->daddr;
	evt->proto = ip->protocol;
	evt->direction = 0; // ingress
	evt->size = size;
	evt->pid = 0;

	__u16 sport = 0, dport = 0;
	if (ip->protocol == IPPROTO_TCP) {
		struct tcphdr *tcp = (void *)(ip + 1);
		if ((void *)(tcp + 1) <= data_end) {
			sport = bpf_ntohs(tcp->source);
			dport = bpf_ntohs(tcp->dest);
		}
	} else if (ip->protocol == IPPROTO_UDP) {
		struct udphdr *udp = (void *)(ip + 1);
		if ((void *)(udp + 1) <= data_end) {
			sport = bpf_ntohs(udp->source);
			dport = bpf_ntohs(udp->dest);
		}
	}
	evt->sport = sport;
	evt->dport = dport;

	bpf_ringbuf_submit(evt, 0);

	// Update per-IP bytes (destination IP)
	bytes = bpf_map_lookup_elem(&ip_bytes, &ip->daddr);
	if (bytes)
		__sync_fetch_and_add(bytes, size);

	return TC_ACT_UNSPEC;
}

SEC("tc_egress")
int tc_egress(struct __sk_buff *skb) {
	__u32 ifindex = skb->ifindex;
	__u8 *found = bpf_map_lookup_elem(&iface_filter, &ifindex);
	if (!found)
		return TC_ACT_UNSPEC;

	void *data = (void *)(long)skb->data;
	void *data_end = (void *)(long)skb->data_end;
	struct ethhdr *eth = data;
	if ((void *)(eth + 1) > data_end)
		return TC_ACT_UNSPEC;

	if (eth->h_proto != bpf_htons(ETH_P_IP))
		return TC_ACT_UNSPEC;

	struct iphdr *ip = (void *)(eth + 1);
	if ((void *)(ip + 1) > data_end)
		return TC_ACT_UNSPEC;

	__u32 size = skb->len;

	struct packet_event *evt = bpf_ringbuf_reserve(&events, sizeof(struct packet_event), 0);
	if (!evt)
		return TC_ACT_UNSPEC;

	evt->timestamp_ns = bpf_ktime_get_ns();
	evt->ifindex = ifindex;
	evt->saddr = ip->saddr;
	evt->daddr = ip->daddr;
	evt->proto = ip->protocol;
	evt->direction = 1; // egress
	evt->size = size;
	evt->pid = 0;

	__u16 sport = 0, dport = 0;
	if (ip->protocol == IPPROTO_TCP) {
		struct tcphdr *tcp = (void *)(ip + 1);
		if ((void *)(tcp + 1) <= data_end) {
			sport = bpf_ntohs(tcp->source);
			dport = bpf_ntohs(tcp->dest);
		}
	} else if (ip->protocol == IPPROTO_UDP) {
		struct udphdr *udp = (void *)(ip + 1);
		if ((void *)(udp + 1) <= data_end) {
			sport = bpf_ntohs(udp->source);
			dport = bpf_ntohs(udp->dest);
		}
	}
	evt->sport = sport;
	evt->dport = dport;

	bpf_ringbuf_submit(evt, 0);
	return TC_ACT_UNSPEC;
}

char _license[] SEC("license") = "GPL";
