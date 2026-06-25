package collector

import (
	"net"
	"sync"
	"time"
)

var privateNetworks []*net.IPNet

func init() {
	for _, cidr := range []string{
		"10.0.0.0/8", "100.64.0.0/10", "172.16.0.0/12", "192.168.0.0/16",
		"127.0.0.0/8", "169.254.0.0/16", "224.0.0.0/4", "240.0.0.0/4",
		"255.255.255.255/32", "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
	} {
		_, network, err := net.ParseCIDR(cidr)
		if err != nil {
			continue
		}
		privateNetworks = append(privateNetworks, network)
	}
}

func IsPrivateIP(ip net.IP) bool {
	if ip == nil {
		return true
	}
	if ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
		ip.IsMulticast() || ip.IsUnspecified() || ip.IsInterfaceLocalMulticast() {
		return true
	}
	for _, nw := range privateNetworks {
		if nw.Contains(ip) {
			return true
		}
	}
	return false
}

func TrafficScope(srcIP, dstIP net.IP) string {
	if IsPrivateIP(srcIP) && IsPrivateIP(dstIP) {
		return "lan"
	}
	return "wan"
}

// CounterData is the JSON-serializable snapshot of a Counter.
type CounterData struct {
	RxBytes   int64 `json:"rxBytes"`
	TxBytes   int64 `json:"txBytes"`
	RxPackets int64 `json:"rxPackets"`
	TxPackets int64 `json:"txPackets"`
	FirstSeen int64 `json:"firstSeen"`
	LastSeen  int64 `json:"lastSeen"`
}

// Counter is a thread-safe monotonic traffic counter.
type Counter struct {
	mu        sync.Mutex
	RxBytes   int64
	TxBytes   int64
	RxPackets int64
	TxPackets int64
	FirstSeen int64
	LastSeen  int64
}

func (c *Counter) Add(direction string, size, packets int64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	now := time.Now().UnixMilli()
	if c.FirstSeen == 0 {
		c.FirstSeen = now
	}
	c.LastSeen = now
	if direction == "rx" {
		c.RxBytes += size
		if packets > 0 {
			c.RxPackets += packets
		} else {
			c.RxPackets++
		}
	} else {
		c.TxBytes += size
		if packets > 0 {
			c.TxPackets += packets
		} else {
			c.TxPackets++
		}
	}
}

func (c *Counter) Snapshot() CounterData {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.FirstSeen == 0 {
		now := time.Now().UnixMilli()
		return CounterData{FirstSeen: now, LastSeen: now}
	}
	return CounterData{
		RxBytes: c.RxBytes, TxBytes: c.TxBytes,
		RxPackets: c.RxPackets, TxPackets: c.TxPackets,
		FirstSeen: c.FirstSeen, LastSeen: c.LastSeen,
	}
}

// PacketEvent represents a single parsed packet.
type PacketEvent struct {
	Timestamp int64                  `json:"timestamp"`
	Iface     string                 `json:"iface"`
	Scope     string                 `json:"scope"`
	Direction string                 `json:"direction"`
	Proto     string                 `json:"proto"`
	Src       string                 `json:"src"`
	Dst       string                 `json:"dst"`
	Sport     int                    `json:"sport"`
	Dport     int                    `json:"dport"`
	Size      int                    `json:"size"`
	Process   map[string]interface{} `json:"process"`
	Weight    int                    `json:"weight"`
}

// ProcInfo identifies a process.
type ProcInfo struct {
	PID       int                    `json:"pid"`
	Name      string                 `json:"name"`
	Cmdline   string                 `json:"cmdline"`
	Container map[string]interface{} `json:"container,omitempty"`
}

// ContainerInfo identifies a Docker container.
type ContainerInfo struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Image    string `json:"image,omitempty"`
	Label    string `json:"label,omitempty"`
	LabelKey string `json:"labelKey,omitempty"`
	HostPort int    `json:"hostPort,omitempty"`
	Proto    string `json:"proto,omitempty"`
}

// InterfaceDetail describes a network interface.
type InterfaceDetail struct {
	Name               string   `json:"name"`
	IsUp               bool     `json:"isUp"`
	Role               string   `json:"role"`
	Note               string   `json:"note"`
	Virtual            bool     `json:"virtual"`
	DefaultRoute       bool     `json:"defaultRoute"`
	CaptureRecommended bool     `json:"captureRecommended"`
	Priority           int      `json:"priority"`
	Captured           bool     `json:"captured"`
	Mac                string   `json:"mac"`
	IPs                []string `json:"ips"`
	SpeedMbps          int      `json:"speedMbps"`
	Mtu                int      `json:"mtu"`
}

// InterfaceRate holds per-interface rate data.
type InterfaceRate struct {
	SystemRxBps float64              `json:"systemRxBps"`
	SystemTxBps float64              `json:"systemTxBps"`
	Scopes      map[string]ScopeRate `json:"scopes"`
}

// ScopeRate is the per-scope byte rate.
type ScopeRate struct {
	RxBps float64 `json:"rxBps"`
	TxBps float64 `json:"txBps"`
}

// SystemCounters holds system-level interface counters.
type SystemCounters struct {
	RxBytes   int64 `json:"rxBytes"`
	TxBytes   int64 `json:"txBytes"`
	RxPackets int64 `json:"rxPackets"`
	TxPackets int64 `json:"txPackets"`
}

// InterfaceState is the full snapshot of an interface.
type InterfaceState struct {
	Detail InterfaceDetail        `json:"detail"`
	Scopes map[string]CounterData `json:"scopes"`
	System SystemCounters         `json:"system"`
}

// ConnectionEntry is a single connection row.
type ConnectionEntry struct {
	Iface      string                 `json:"iface"`
	Scope      string                 `json:"scope"`
	Proto      string                 `json:"proto"`
	Source     string                 `json:"source"`
	Dest       string                 `json:"dest"`
	Direction  string                 `json:"direction"`
	RxBytes    int64                  `json:"rxBytes"`
	TxBytes    int64                  `json:"txBytes"`
	TotalBytes int64                  `json:"totalBytes"`
	RxPackets  int64                  `json:"rxPackets"`
	TxPackets  int64                  `json:"txPackets"`
	FirstSeen  float64                `json:"firstSeen"`
	LastSeen   float64                `json:"lastSeen"`
	Duration   float64                `json:"durationSeconds"`
	Process    map[string]interface{} `json:"process"`
}

// ConnectionSummary is the active connection count summary.
type ConnectionSummary struct {
	Total int `json:"total"`
	WAN   int `json:"wan"`
	LAN   int `json:"lan"`
}

// ConntrackSummary holds conntrack stats.
type ConntrackSummary struct {
	Available    bool   `json:"available"`
	Source       string `json:"source"`
	Total        int    `json:"total"`
	WAN          int    `json:"wan"`
	LAN          int    `json:"lan"`
	RawTotal     int    `json:"rawTotal"`
	Mode         string `json:"mode"`
	Truncated    bool   `json:"truncated"`
	ScannedLines int    `json:"scannedLines"`
}

// ProcessEntry is a ranked process row.
type ProcessEntry struct {
	PID             int                    `json:"pid"`
	Name            string                 `json:"name"`
	Cmdline         string                 `json:"cmdline"`
	Container       map[string]interface{} `json:"container"`
	CounterData                              // embedded
	TotalBytes      int64                  `json:"totalBytes"`
	DurationSeconds float64                `json:"durationSeconds"`
}

// CaptureDiagnostics holds capture engine stats.
type CaptureDiagnostics struct {
	Enabled            bool     `json:"enabled"`
	Interfaces         []string `json:"interfaces"`
	SeenEvents         int64    `json:"seenEvents"`
	RecordedEvents     int64    `json:"recordedEvents"`
	DroppedEvents      int64    `json:"droppedEvents"`
	SampledEvents      int64    `json:"sampledEvents"`
	WeightedBytes      int64    `json:"weightedBytes"`
	MaxEventsPerSecond int      `json:"maxEventsPerSecond"`
	SampleRate         int      `json:"sampleRate"`
	DynamicSample      bool     `json:"dynamicSample"`
	MaxSampleRate      int      `json:"maxSampleRate"`
}

// CacheDiagnostics holds cache size info.
type CacheDiagnostics struct {
	ConnectionCount      int `json:"connectionTotals"`
	ProcessCount         int `json:"processTotals"`
	PortCount            int `json:"portTotals"`
	SocketMapSize        int `json:"socketMap"`
	RecentProcessKeys    int `json:"processRecentKeys"`
	RecentProcessBuckets int `json:"processRecentBuckets"`
}

// MemoryDiagnostics holds memory stats.
type MemoryDiagnostics struct {
	RSSBytes int64 `json:"rssBytes"`
	VMSBytes int64 `json:"vmsBytes"`
}

// DiagnosticsResponse is the full diagnostics payload.
type DiagnosticsResponse struct {
	Timestamp float64             `json:"timestamp"`
	Capture   CaptureDiagnostics  `json:"capture"`
	Caches    CacheDiagnostics    `json:"caches"`
	Conntrack ConntrackSummary    `json:"conntrack"`
	Memory    MemoryDiagnostics   `json:"memory"`
}

// SnapshotResponse is the full snapshot payload.
type SnapshotResponse struct {
	Timestamp         float64                   `json:"timestamp"`
	Interfaces        map[string]InterfaceState `json:"interfaces"`
	Rates             map[string]InterfaceRate  `json:"rates"`
	ConnectionSummary ConnectionSummary         `json:"connectionSummary"`
	ConntrackSummary  ConntrackSummary          `json:"conntrackSummary,omitempty"`
	Connections       []ConnectionEntry         `json:"connections,omitempty"`
	Processes         []ProcessEntry            `json:"processes,omitempty"`
	CaptureInterfaces []string                  `json:"captureInterfaces"`
}
