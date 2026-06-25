package collector

import "testing"

func TestBuildEventKeepsPlainIPsForMatchingAndEndpointsForDisplay(t *testing.T) {
	agg := NewAggregator()
	engine := NewCaptureEngine(agg, CaptureConfig{})
	engine.UpdateLocalAddrs(map[string]bool{"192.168.3.56": true})

	event := engine.buildEventFromFields("eth1", 1500, "192.168.3.56", "8.8.8.8", "tcp", 50000, 443)
	if event == nil {
		t.Fatal("expected event")
	}
	if event.SrcIP != "192.168.3.56" {
		t.Fatalf("SrcIP = %q, want plain local IP", event.SrcIP)
	}
	if event.DstIP != "8.8.8.8" {
		t.Fatalf("DstIP = %q, want plain remote IP", event.DstIP)
	}
	if event.Src != "192.168.3.56:50000" {
		t.Fatalf("Src = %q, want endpoint text", event.Src)
	}
	if event.Dst != "8.8.8.8:443" {
		t.Fatalf("Dst = %q, want endpoint text", event.Dst)
	}
	if event.Direction != "tx" {
		t.Fatalf("Direction = %q, want tx", event.Direction)
	}
	if event.Size != 1500 {
		t.Fatalf("Size = %d, want 1500", event.Size)
	}
}

func TestFindProcessUsesPlainIPsFromPacketEvent(t *testing.T) {
	agg := NewAggregator()
	engine := NewCaptureEngine(agg, CaptureConfig{})
	engine.UpdateLocalAddrs(map[string]bool{"192.168.3.56": true})
	engine.UpdateSocketMap(map[string]ProcInfo{
		"tcp|192.168.3.56|8.8.8.8|50000|443": {PID: 1234, Name: "xunlei"},
	})

	event := engine.buildEventFromFields("eth1", 1200, "192.168.3.56", "8.8.8.8", "tcp", 50000, 443)
	proc := engine.processForEvent(event)
	if proc.Name != "xunlei" || proc.PID != 1234 {
		t.Fatalf("process = %+v, want xunlei pid 1234", proc)
	}
}
