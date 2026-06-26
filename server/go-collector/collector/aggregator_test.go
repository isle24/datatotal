package collector

import (
	"testing"
	"time"
)

func TestConnectionEntriesFiltersSortsAndPaginates(t *testing.T) {
	agg := NewAggregator()
	nowMs := nowUnixMillis()
	agg.ConnTotals["eth1|wan|tcp|192.168.3.56:50000|8.8.8.8:443|"+ProcessKeyFor(ProcInfo{PID: 1, Name: "xunlei"}, ContainerInfo{}, false)] = &Counter{
		RxBytes: 9000, TxBytes: 1000, FirstSeen: nowMs - 1000, LastSeen: nowMs,
	}
	agg.ConnTotals["eth1|lan|tcp|192.168.3.56:50001|192.168.3.1:80|"+ProcessKeyFor(ProcInfo{PID: 2, Name: "router"}, ContainerInfo{}, false)] = &Counter{
		RxBytes: 2000, TxBytes: 1000, FirstSeen: nowMs - 1000, LastSeen: nowMs,
	}
	agg.ConnTotals["eth2|wan|udp|192.168.3.56:6881|1.1.1.1:6881|"+ProcessKeyFor(ProcInfo{PID: 3, Name: "qbittorrent"}, ContainerInfo{}, false)] = &Counter{
		RxBytes: 100, TxBytes: 50000, FirstSeen: nowMs - 1000, LastSeen: nowMs,
	}

	rows, page, summary := agg.ConnectionEntries(120, 1, 0, ConnectionFilters{Scope: "wan", Direction: "tx", Owner: "qbittorrent"})
	if page.Total != 1 || page.Pages != 1 || page.Limit != 1 || page.Offset != 0 {
		t.Fatalf("page = %+v, want one filtered result", page)
	}
	if summary.Total != 1 || summary.WAN != 1 || summary.LAN != 0 {
		t.Fatalf("summary = %+v, want one wan result", summary)
	}
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want 1", len(rows))
	}
	if rows[0].Process["name"] != "qbittorrent" {
		t.Fatalf("owner = %v, want qbittorrent", rows[0].Process["name"])
	}
	if rows[0].TxBytes != 50000 {
		t.Fatalf("TxBytes = %d, want largest tx row", rows[0].TxBytes)
	}
}

func TestConnectionEntriesReturnsEmptySliceAndPagination(t *testing.T) {
	agg := NewAggregator()
	rows, page, summary := agg.ConnectionEntries(120, 20, 0, ConnectionFilters{Scope: "wan"})
	if rows == nil {
		t.Fatal("rows is nil, want empty slice")
	}
	if len(rows) != 0 {
		t.Fatalf("len(rows) = %d, want 0", len(rows))
	}
	if page.Total != 0 || page.Pages != 1 {
		t.Fatalf("page = %+v, want empty first page", page)
	}
	if summary.Total != 0 || summary.WAN != 0 || summary.LAN != 0 {
		t.Fatalf("summary = %+v, want zero summary", summary)
	}
}

func TestRecordConnectionUsesEndpointOnce(t *testing.T) {
	agg := NewAggregator()
	agg.Record(PacketEvent{
		Timestamp: nowUnixMillis(),
		Iface:     "eth0",
		Scope:     "wan",
		Direction: "tx",
		Proto:     "tcp",
		SrcIP:     "192.168.3.56",
		DstIP:     "8.8.8.8",
		Src:       "192.168.3.56:50000",
		Dst:       "8.8.8.8:443",
		Sport:     50000,
		Dport:     443,
		Size:      1000,
		Process:   map[string]interface{}{"pid": 1, "name": "xunlei"},
		Weight:    1,
	})

	rows, _, _ := agg.ConnectionEntries(120, 20, 0, ConnectionFilters{})
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want 1", len(rows))
	}
	if rows[0].Source != "192.168.3.56:50000" {
		t.Fatalf("Source = %q, want endpoint once", rows[0].Source)
	}
	if rows[0].Dest != "8.8.8.8:443" {
		t.Fatalf("Dest = %q, want endpoint once", rows[0].Dest)
	}
}

func nowUnixMillis() int64 {
	return time.Now().UnixMilli()
}
