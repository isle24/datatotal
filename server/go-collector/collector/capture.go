package collector

import (
	"fmt"
	"log"
	"net"
	"strings"
	"sync"
	"time"

	"github.com/google/gopacket"
	"github.com/google/gopacket/layers"
	"github.com/google/gopacket/pcap"
)

type CaptureEngine struct {
	mu               sync.Mutex
	handles          map[string]*pcap.Handle
	aggregator       *Aggregator
	localAddrs       map[string]bool
	socketMap        map[string]ProcInfo
	socketMapMu      sync.RWMutex
	containerPorts   map[string]ContainerInfo
	containerPortsMu sync.RWMutex
	captureIfaces    []string
	running          bool

	MaxEventsPerSecond int
	BaseSampleRate     int
	MaxSampleRate      int
	DynamicSample      bool
}

type CaptureConfig struct {
	Interfaces         []string
	MaxEventsPerSecond int
	BaseSampleRate     int
	MaxSampleRate      int
	DynamicSample      bool
}

func DefaultCaptureConfig() CaptureConfig {
	return CaptureConfig{
		MaxEventsPerSecond: 2000,
		BaseSampleRate:     1,
		MaxSampleRate:      50,
		DynamicSample:      true,
	}
}

func NewCaptureEngine(aggregator *Aggregator, config CaptureConfig) *CaptureEngine {
	return &CaptureEngine{
		handles:            make(map[string]*pcap.Handle),
		aggregator:         aggregator,
		localAddrs:         make(map[string]bool),
		socketMap:          make(map[string]ProcInfo),
		containerPorts:     make(map[string]ContainerInfo),
		captureIfaces:      config.Interfaces,
		MaxEventsPerSecond: config.MaxEventsPerSecond,
		BaseSampleRate:     config.BaseSampleRate,
		MaxSampleRate:      config.MaxSampleRate,
		DynamicSample:      config.DynamicSample,
	}
}

func (ce *CaptureEngine) SetInterfaces(ifaces []string) {
	ce.mu.Lock()
	defer ce.mu.Unlock()
	ce.captureIfaces = ifaces
}

func (ce *CaptureEngine) GetInterfaces() []string {
	ce.mu.Lock()
	defer ce.mu.Unlock()
	result := make([]string, len(ce.captureIfaces))
	copy(result, ce.captureIfaces)
	return result
}

func (ce *CaptureEngine) UpdateSocketMap(m map[string]ProcInfo) {
	ce.socketMapMu.Lock()
	defer ce.socketMapMu.Unlock()
	ce.socketMap = m
}

func (ce *CaptureEngine) UpdateLocalAddrs(addrs map[string]bool) {
	ce.mu.Lock()
	defer ce.mu.Unlock()
	ce.localAddrs = addrs
}

func (ce *CaptureEngine) UpdateContainerPorts(ports map[string]ContainerInfo) {
	ce.containerPortsMu.Lock()
	defer ce.containerPortsMu.Unlock()
	ce.containerPorts = ports
}

func (ce *CaptureEngine) findProcess(proto, localIP, remoteIP string, localPort, remotePort int) ProcInfo {
	ce.socketMapMu.RLock()
	defer ce.socketMapMu.RUnlock()

	keys := []string{
		fmt.Sprintf("%s|%s|%s|%d|%d", proto, localIP, remoteIP, localPort, remotePort),
		fmt.Sprintf("%s|0.0.0.0|%s|%d|%d", proto, remoteIP, localPort, remotePort),
		fmt.Sprintf("%s|::|%s|%d|%d", proto, remoteIP, localPort, remotePort),
		fmt.Sprintf("%s|%s|0.0.0.0|%d|0", proto, localIP, localPort),
		fmt.Sprintf("%s|%s|::|%d|0", proto, localIP, localPort),
		fmt.Sprintf("%s|0.0.0.0|0.0.0.0|%d|0", proto, localPort),
		fmt.Sprintf("%s|::|::|%d|0", proto, localPort),
	}
	for _, key := range keys {
		if proc, ok := ce.socketMap[key]; ok {
			return proc
		}
	}
	return ProcInfo{PID: 0, Name: "unknown"}
}

func (ce *CaptureEngine) findContainer(proto string, ports []int) ContainerInfo {
	ce.containerPortsMu.RLock()
	defer ce.containerPortsMu.RUnlock()
	for _, port := range ports {
		key := fmt.Sprintf("%s:%d", proto, port)
		if ci, ok := ce.containerPorts[key]; ok {
			return ci
		}
	}
	return ContainerInfo{}
}

func (ce *CaptureEngine) Start(ifaces []string) error {
	ce.mu.Lock()
	defer ce.mu.Unlock()

	if ce.running {
		return nil
	}
	if len(ifaces) == 0 {
		ifaces = ce.captureIfaces
	}
	ce.captureIfaces = ifaces

	for _, iface := range ifaces {
		handle, err := pcap.OpenLive(iface, 65535, false, 500*time.Millisecond)
		if err != nil {
			log.Printf("go-collector: failed to open %s: %v", iface, err)
			continue
		}
		if err := handle.SetBPFFilter("ip or ip6"); err != nil {
			log.Printf("go-collector: failed to set BPF filter on %s: %v", iface, err)
		}
		ce.handles[iface] = handle
		log.Printf("go-collector: capturing on %s", iface)
	}

	ce.running = true
	for iface, handle := range ce.handles {
		go ce.captureLoop(iface, handle)
	}
	return nil
}

func (ce *CaptureEngine) Stop() {
	ce.mu.Lock()
	defer ce.mu.Unlock()
	ce.running = false
	for iface, handle := range ce.handles {
		handle.Close()
		delete(ce.handles, iface)
	}
}

func (ce *CaptureEngine) captureLoop(iface string, handle *pcap.Handle) {
	ps := gopacket.NewPacketSource(handle, handle.LinkType())
	ps.NoCopy = true
	ps.Lazy = true

	for packet := range ps.Packets() {
		ce.mu.Lock()
		if !ce.running {
			ce.mu.Unlock()
			return
		}
		ce.mu.Unlock()

		weight := ce.aggregator.PacketWeight(ce.MaxEventsPerSecond, ce.BaseSampleRate, ce.MaxSampleRate, ce.DynamicSample)
		if weight <= 0 {
			continue
		}

		event := ce.parsePacket(iface, packet)
		if event == nil {
			continue
		}

		// Determine direction
		localIP, remoteIP := event.Src, event.Dst
		localPort, remotePort := event.Sport, event.Dport
		if event.Direction == "rx" {
			localIP, remoteIP = event.Dst, event.Src
			localPort, remotePort = event.Dport, event.Sport
		}

		proc := ce.findProcess(event.Proto, localIP, remoteIP, localPort, remotePort)
		event.Process = map[string]interface{}{
			"pid": proc.PID, "name": proc.Name, "cmdline": proc.Cmdline,
		}

		ci := ce.findContainer(event.Proto, []int{localPort, remotePort})
		if ci.Name != "" {
			event.Process["container"] = map[string]interface{}{
				"id": ci.ID, "name": ci.Name, "image": ci.Image,
				"label": ci.Label, "labelKey": ci.LabelKey,
				"hostPort": ci.HostPort, "proto": ci.Proto,
			}
		}

		event.Weight = weight
		ce.aggregator.Record(*event)
	}
}

func (ce *CaptureEngine) parsePacket(iface string, packet gopacket.Packet) *PacketEvent {
	if ipLayer := packet.Layer(layers.LayerTypeIPv4); ipLayer != nil {
		return ce.buildEvent(iface, packet, ipLayer.(*layers.IPv4))
	}
	if ip6Layer := packet.Layer(layers.LayerTypeIPv6); ip6Layer != nil {
		return ce.buildEvent(iface, packet, ip6Layer.(*layers.IPv6))
	}
	return nil
}

func (ce *CaptureEngine) buildEvent(iface string, packet gopacket.Packet, ipLayer interface{}) *PacketEvent {
	var srcIP, dstIP string
	switch ip := ipLayer.(type) {
	case *layers.IPv4:
		srcIP = ip.SrcIP.String()
		dstIP = ip.DstIP.String()
	case *layers.IPv6:
		srcIP = ip.SrcIP.String()
		dstIP = ip.DstIP.String()
	default:
		return nil
	}
	return ce.buildEventWithIPs(iface, packet, srcIP, dstIP)
}

func (ce *CaptureEngine) buildEventWithIPs(iface string, packet gopacket.Packet, srcIP, dstIP string) *PacketEvent {
	var proto string
	var sport, dport int

	if tcp := packet.Layer(layers.LayerTypeTCP); tcp != nil {
		t := tcp.(*layers.TCP)
		proto = "tcp"
		sport = int(t.SrcPort)
		dport = int(t.DstPort)
	} else if udp := packet.Layer(layers.LayerTypeUDP); udp != nil {
		u := udp.(*layers.UDP)
		proto = "udp"
		sport = int(u.SrcPort)
		dport = int(u.DstPort)
	} else {
		return nil
	}

	src := net.ParseIP(srcIP)
	dst := net.ParseIP(dstIP)
	scope := TrafficScope(src, dst)

	ce.mu.Lock()
	localAddrs := ce.localAddrs
	ce.mu.Unlock()

	var direction string
	srcLocal := localAddrs[srcIP]
	dstLocal := localAddrs[dstIP]

	if srcLocal && !dstLocal {
		direction = "tx"
	} else if dstLocal && !srcLocal {
		direction = "rx"
	} else if IsPrivateIP(src) {
		direction = "tx"
	} else {
		direction = "rx"
	}

	return &PacketEvent{
		Timestamp: time.Now().UnixMilli(),
		Iface:     iface,
		Scope:     scope,
		Direction: direction,
		Proto:     proto,
		Src:       formatEndpoint(srcIP, sport),
		Dst:       formatEndpoint(dstIP, dport),
		Sport:     sport,
		Dport:     dport,
		Size:      len(packet.Data()),
	}
}

func formatEndpoint(ip string, port int) string {
	if strings.Contains(ip, ":") && !strings.HasPrefix(ip, "[") {
		return fmt.Sprintf("[%s]:%d", ip, port)
	}
	return fmt.Sprintf("%s:%d", ip, port)
}
