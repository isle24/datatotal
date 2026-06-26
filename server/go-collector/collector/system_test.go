package collector

import (
	"os"
	"testing"
	"time"
)

func TestDecodeHexAddrIPv4UsesProcNetLittleEndian(t *testing.T) {
	ip, port := decodeHexAddr("3803A8C0:C350")
	if ip != "192.168.3.56" {
		t.Fatalf("ip = %q, want 192.168.3.56", ip)
	}
	if port != 50000 {
		t.Fatalf("port = %d, want 50000", port)
	}
}

func TestConntrackReadConnectionsFiltersWanScope(t *testing.T) {
	path := t.TempDir() + "/nf_conntrack"
	content := "" +
		"ipv4 2 tcp 6 431999 ESTABLISHED src=192.168.3.56 dst=8.8.8.8 sport=50000 dport=443 packets=10 bytes=1000 src=8.8.8.8 dst=192.168.3.56 sport=443 dport=50000 packets=20 bytes=2000 [ASSURED] mark=0 use=1\n" +
		"ipv4 2 tcp 6 431999 ESTABLISHED src=192.168.3.56 dst=192.168.3.1 sport=50001 dport=80 packets=3 bytes=300 src=192.168.3.1 dst=192.168.3.56 sport=80 dport=50001 packets=4 bytes=400 [ASSURED] mark=0 use=1\n"
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}

	reader := NewConntrackReader("active", []string{"ESTABLISHED"}, true, false, 3)
	reader.paths = []string{path}

	rows := reader.ReadConnections(100, time.Second, ConnectionFilters{Scope: "wan"})
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want one wan connection", len(rows))
	}
	if rows[0].Scope != "wan" {
		t.Fatalf("Scope = %q, want wan", rows[0].Scope)
	}
}
