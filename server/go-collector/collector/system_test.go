package collector

import "testing"

func TestDecodeHexAddrIPv4UsesProcNetLittleEndian(t *testing.T) {
	ip, port := decodeHexAddr("3803A8C0:C350")
	if ip != "192.168.3.56" {
		t.Fatalf("ip = %q, want 192.168.3.56", ip)
	}
	if port != 50000 {
		t.Fatalf("port = %d, want 50000", port)
	}
}
