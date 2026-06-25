// Package ebpf provides a TC (Traffic Control) based eBPF collector.
// It attaches eBPF programs to network interfaces for zero-copy packet
// accounting, with a perf ring buffer fallback if BTF is unavailable.
//
// This package only compiles on Linux (requires cilium/ebpf).
// On non-Linux platforms, the entire package is omitted via build tags.

//go:build linux && cgo
// +build linux,cgo

package ebpf

import (
	"encoding/binary"
	"fmt"
	"log"
	"net"
	"sync"
	"time"
	"unsafe"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/link"
	"github.com/cilium/ebpf/ringbuf"
	"github.com/cilium/ebpf/rlimit"
)

// PacketEvent matches the C struct packet_event in traffic_kern.c
type PacketEvent struct {
	TimestampNs uint64
	Ifindex     uint32
	Saddr       uint32
	Daddr       uint32
	Sport       uint16
	Dport       uint16
	Proto       uint8
	Direction   uint8
	Size        uint32
	PID         uint32
}

// Collector attaches eBPF TC programs to specified interfaces
// and reads packet events from a ring buffer.
type Collector struct {
	mu         sync.Mutex
	objs       *trafficObjects
	links       []link.Link
	eventCh     chan PacketEvent
	running     bool
	ifaces      []string
	ringReader  *ringbuf.Reader
}

//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -target amd64 traffic traffic_kern.c -- -I/usr/include -I/usr/include/x86_64-linux-gnu -O2 -Wall

type trafficObjects struct {
	Events      *ebpf.Map `ebpf:"events"`
	IfaceFilter *ebpf.Map `ebpf:"iface_filter"`
	IpBytes     *ebpf.Map `ebpf:"ip_bytes"`
	TcIngress   *ebpf.Program `ebpf:"tc_ingress"`
	TcEgress    *ebpf.Program `ebpf:"tc_egress"`
}

func NewCollector(ifaces []string) (*Collector, error) {
	if err := rlimit.RemoveMemlock(); err != nil {
		log.Printf("ebpf: failed to remove memlock: %v", err)
		return nil, err
	}

	c := &Collector{
		eventCh: make(chan PacketEvent, 4096),
		ifaces:  ifaces,
	}
	return c, nil
}

func (c *Collector) Start() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.running {
		return nil
	}

	// Load compiled eBPF program
	objs := &trafficObjects{}
	if err := loadTrafficObjects(objs, nil); err != nil {
		return fmt.Errorf("ebpf: failed to load objects: %w", err)
	}
	c.objs = objs

	// Populate interface filter map
	for _, iface := range c.ifaces {
		ifi, err := net.InterfaceByName(iface)
		if err != nil {
			log.Printf("ebpf: skip iface %s: %v", iface, err)
			continue
		}
		idx := uint32(ifi.Index)
		val := uint8(1)
		if err := objs.IfaceFilter.Put(&idx, &val); err != nil {
			log.Printf("ebpf: failed to add iface filter for %s: %v", iface, err)
			continue
		}

		// Attach ingress
		ingLink, err := link.AttachTCX(link.TCXOptions{
			Interface: ifi.Index,
			Program:   objs.TcIngress,
			Attach:    ebpf.AttachTCXIngress,
		})
		if err != nil {
			log.Printf("ebpf: TCX ingress attach failed on %s: %v (falling back to TC)", iface, err)
			ingLink, err = link.AttachTC(ifi.Index, objs.TcIngress, "ingress")
			if err != nil {
				log.Printf("ebpf: TC ingress attach also failed on %s: %v", iface, err)
				continue
			}
		}
		c.links = append(c.links, ingLink)

		// Attach egress
		egLink, err := link.AttachTCX(link.TCXOptions{
			Interface: ifi.Index,
			Program:   objs.TcEgress,
			Attach:    ebpf.AttachTCXEgress,
		})
		if err != nil {
			log.Printf("ebpf: TCX egress attach failed on %s: %v", iface, err)
			continue
		}
		c.links = append(c.links, egLink)

		log.Printf("ebpf: attached to %s (index=%d)", iface, ifi.Index)
	}

	// Open ring buffer reader
	rd, err := ringbuf.NewReader(objs.Events)
	if err != nil {
		c.cleanup()
		return fmt.Errorf("ebpf: ring buffer open failed: %w", err)
	}
	c.ringReader = rd
	c.running = true

	go c.readLoop()
	return nil
}

func (c *Collector) Stop() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.running = false
	c.cleanup()
}

func (c *Collector) cleanup() {
	for _, l := range c.links {
		l.Close()
	}
	c.links = nil
	if c.objs != nil {
		c.objs.Close()
		c.objs = nil
	}
	if c.ringReader != nil {
		c.ringReader.Close()
		c.ringReader = nil
	}
}

func (c *Collector) readLoop() {
	for c.running {
		record, err := c.ringReader.Read()
		if err != nil {
			if c.running {
				log.Printf("ebpf: ringbuf read error: %v", err)
			}
			continue
		}
		var evt PacketEvent
		if len(record.RawSample) >= int(unsafe.Sizeof(evt)) {
			evt = *(*PacketEvent)(unsafe.Pointer(&record.RawSample[0]))
			c.eventCh <- evt
		}
	}
}

// Events returns the channel of packet events for downstream consumption.
func (c *Collector) Events() <-chan PacketEvent {
	return c.eventCh
}

// IPString converts a uint32 IP to dotted-quad string.
func IPString(ip uint32) string {
	b := make([]byte, 4)
	binary.LittleEndian.PutUint32(b, ip)
	return net.IP(b).String()
}

// Uint32ToIP converts uint32 to net.IP.
func Uint32ToIP(ip uint32) net.IP {
	b := make([]byte, 4)
	binary.LittleEndian.PutUint32(b, ip)
	return net.IP(b)
}
