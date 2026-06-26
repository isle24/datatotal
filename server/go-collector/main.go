package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"nas-traffic-lens/go-collector/collector"
)

var (
	listenPort       = flag.Int("port", 18088, "HTTP listen port")
	sampleSecondsF   = flag.Float64("sample-seconds", 1.0, "Sample interval in seconds")
	captureIFacesF   = flag.String("capture-interfaces", "", "Capture interfaces (comma separated, auto if empty)")
	maxEventsPerSecF = flag.Int("max-events-per-second", 2000, "Max packet events per second")
	baseSampleRateF  = flag.Int("sample-rate", 1, "Base sample rate")
	maxSampleRateF   = flag.Int("max-sample-rate", 50, "Max dynamic sample rate")
	dynamicSampleF   = flag.Bool("dynamic-sample", true, "Enable dynamic sampling")
	sockRefreshSecF  = flag.Int("socket-refresh", 60, "Socket map refresh interval")
	ctRefreshSecF    = flag.Int("conntrack-refresh", 30, "Conntrack refresh interval")
	ctMaxLinesF      = flag.Int("conntrack-max-lines", 30000, "Conntrack max scan lines")
	procRecentSecF   = flag.Int("process-recent-sec", 180, "Process recent memory window")
	maxConnF         = flag.Int("max-conn-tracked", 10000, "Max tracked connections")
	maxProcF         = flag.Int("max-proc-tracked", 2048, "Max tracked processes")
	maxPortF         = flag.Int("max-port-tracked", 4096, "Max tracked ports")
	procScanTimeoutF = flag.Int("proc-scan-timeout", 1, "Proc scan timeout in seconds")
	maxFDLinksF      = flag.Int("max-fd-links", 60000, "Max fd links per scan")
	maxNetLinesF     = flag.Int("max-net-lines", 60000, "Max proc/net lines per file")
	ctModeF          = flag.String("conntrack-mode", "active", "Conntrack mode: active or raw")
	ctTCPStatesF     = flag.String("conntrack-tcp-states", "ESTABLISHED", "TCP states for active mode")
	ctUDPAssuredF    = flag.Bool("conntrack-udp-assured", true, "UDP require ASSURED flag")
)

func main() {
	flag.Parse()

	portNum := envInt("GO_COLLECTOR_PORT", *listenPort)
	sampleSec := envFloat("SAMPLE_SECONDS", *sampleSecondsF)
	ifaceStr := envStr("CAPTURE_INTERFACES", *captureIFacesF)
	maxEPS := envInt("CAPTURE_MAX_EVENTS_PER_SECOND", *maxEventsPerSecF)
	bsr := envInt("CAPTURE_SAMPLE_RATE", *baseSampleRateF)
	msr := envInt("CAPTURE_MAX_SAMPLE_RATE", *maxSampleRateF)
	ds := envBool("CAPTURE_DYNAMIC_SAMPLE", *dynamicSampleF)
	sr := envInt("SOCKET_REFRESH_SECONDS", *sockRefreshSecF)
	crs := envInt("CONNTRACK_REFRESH_SECONDS", *ctRefreshSecF)
	cml := envInt("CONNTRACK_MAX_LINES", *ctMaxLinesF)
	prs := envInt("PROCESS_RECENT_SECONDS", *procRecentSecF)
	mct := envInt("MAX_CONNECTION_TRACKED", *maxConnF)
	mpt := envInt("MAX_PROCESS_TRACKED", *maxProcF)
	mpt2 := envInt("MAX_PORT_TRACKED", *maxPortF)
	pst := envInt("PROC_SCAN_TIMEOUT_SECONDS", *procScanTimeoutF)
	mfl := envInt("MAX_PROC_FD_LINKS", *maxFDLinksF)
	mnl := envInt("MAX_PROC_NET_LINES", *maxNetLinesF)
	cm := envStr("CONNTRACK_COUNT_MODE", *ctModeF)
	cts := envStr("CONNTRACK_TCP_STATES", *ctTCPStatesF)
	cua := envBool("CONNTRACK_UDP_REQUIRE_ASSURED", *ctUDPAssuredF)

	listenAddr := fmt.Sprintf(":%d", portNum)
	log.Printf("go-collector starting on %s", listenAddr)
	log.Printf("go-collector: sample=%.1fs max_eps=%d dynamic=%v", sampleSec, maxEPS, ds)

	agg := collector.NewAggregator()

	details := collector.GetInterfaceDetails(nil)
	captureList := collector.DetermineCaptureInterfaces(details, ifaceStr)
	log.Printf("go-collector: capture interfaces: %v", captureList)

	captured := make(map[string]bool)
	for _, name := range captureList {
		captured[name] = true
	}

	cfg := collector.CaptureConfig{
		Interfaces:         captureList,
		MaxEventsPerSecond: maxEPS,
		BaseSampleRate:     bsr,
		MaxSampleRate:      msr,
		DynamicSample:      ds,
	}
	captureEng := collector.NewCaptureEngine(agg, cfg)

	socketMapper := collector.NewSocketMapper()

	tcpStates := strings.Split(cts, ",")
	ctReader := collector.NewConntrackReader(cm, tcpStates, cua, false, 3)

	if err := captureEng.Start(captureList); err != nil {
		log.Printf("go-collector: capture start error: %v", err)
	}

	// background: socket map
	go func() {
		for {
			socketMapper.Refresh(time.Duration(pst)*time.Second, mfl, mnl)
			captureEng.UpdateSocketMap(socketMapper.GetMap())
			time.Sleep(time.Duration(sr) * time.Second)
		}
	}()

	// background: local addresses
	go func() {
		for {
			captureEng.UpdateLocalAddrs(collector.GetLocalAddresses())
			time.Sleep(time.Duration(sr) * time.Second)
		}
	}()

	// background: cache trim
	go func() {
		for {
			agg.TrimCaches(mct, mpt, mpt2, int64(prs))
			agg.PruneConnections(int64(900))
			time.Sleep(10 * time.Second)
		}
	}()

	// background: conntrack refresh
	go func() {
		for {
			_ = ctReader.ReadSummary(cml, 1*time.Second)
			time.Sleep(time.Duration(crs) * time.Second)
		}
	}()

	// background: rate calculation
	type rateCache struct {
		mu    sync.RWMutex
		rates map[string]collector.InterfaceRate
	}
	rc := &rateCache{}

	go func() {
		var prev map[string]collector.InterfaceState
		var prevT float64
		for {
			d := collector.GetInterfaceDetails(captured)
			sysIO := collector.GetSystemIO()
			cur := agg.SnapshotInterfaces(sysIO, d)
			n := float64(time.Now().UnixNano()) / 1e9
			if prev != nil && prevT > 0 {
				elapsed := n - prevT
				if elapsed > 0 {
					rc.mu.Lock()
					rc.rates = agg.DiffRates(prev, cur, elapsed)
					rc.mu.Unlock()
				}
			}
			prev = cur
			prevT = n
			time.Sleep(time.Duration(sampleSec * float64(time.Second)))
		}
	}()

	mux := http.NewServeMux()

	mux.HandleFunc("/api/snapshot", func(w http.ResponseWriter, r *http.Request) {
		d := collector.GetInterfaceDetails(captured)
		sysIO := collector.GetSystemIO()
		ifaces := agg.SnapshotInterfaces(sysIO, d)

		rc.mu.RLock()
		rates := rc.rates
		rc.mu.RUnlock()
		if rates == nil {
			rates = make(map[string]collector.InterfaceRate)
		}

		ifaceNames := make(map[string]bool, len(ifaces))
		for name := range ifaces {
			ifaceNames[name] = true
		}
		stageActive, stageStartedAt, stageIfaces := agg.StageSnapshot()

		writeJSON(w, collector.SnapshotResponse{
			Timestamp:         float64(time.Now().UnixNano()) / 1e9,
			Interfaces:        ifaces,
			Rates:             rates,
			ConnectionSummary: agg.ConnectionCounts(120, ifaceNames),
			ConntrackSummary:  ctReader.ReadSummary(cml, 1*time.Second),
			CaptureInterfaces: captureList,
			Stage: collector.StageResponse{
				Active:     stageActive,
				StartedAt:  stageStartedAt,
				Interfaces: stageIfaces,
			},
		})
	})

	mux.HandleFunc("/api/processes", func(w http.ResponseWriter, r *http.Request) {
		period := r.URL.Query().Get("period")
		if period == "" {
			period = "30s"
		}
		limit := 30
		if v := r.URL.Query().Get("limit"); v != "" {
			if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 100 {
				limit = n
			}
		}
		nowUnix := time.Now().Unix()
		startSec := nowUnix - 30
		endSec := nowUnix
		switch period {
		case "today":
			now := time.Now()
			startSec = now.Unix() - int64(now.Hour()*3600+now.Minute()*60+now.Second())
		case "3d":
			startSec = nowUnix - 3*86400
		case "7d":
			startSec = nowUnix - 7*86400
		case "30d":
			startSec = nowUnix - 30*86400
		}
		entries := agg.ProcessRankFromEvents(startSec, endSec, limit)
		writeJSON(w, map[string]interface{}{
			"period":    period,
			"start":     startSec,
			"end":       endSec,
			"source":    "memory",
			"processes": entries,
		})
	})

	mux.HandleFunc("/api/connections", func(w http.ResponseWriter, r *http.Request) {
		mode := r.URL.Query().Get("mode")
		limit := queryInt(r, "limit", 120, 1, 300)
		offset := queryInt(r, "offset", 0, 0, 1000000)
		filters := collector.ConnectionFilters{
			Iface:       defaultQuery(r, "iface", "all"),
			Scope:       defaultQuery(r, "scope", "all"),
			Proto:       defaultQuery(r, "proto", "all"),
			Direction:   defaultQuery(r, "direction", "all"),
			Owner:       r.URL.Query().Get("owner"),
			Source:      r.URL.Query().Get("source"),
			Dest:        r.URL.Query().Get("dest"),
			MinBytes:    int64(queryInt(r, "min_bytes", 0, 0, 1_000_000_000_000_000)),
			MinDuration: int64(queryInt(r, "min_duration", 0, 0, 31_536_000)),
		}
		if mode == "conntrack" {
			conns := ctReader.ReadConnections(cml, 1500*time.Millisecond, filters)
			if conns == nil {
				conns = []collector.ConnectionEntry{}
			}
			total := len(conns)
			if offset > total {
				offset = total
			}
			end := offset + limit
			if end > total {
				end = total
			}
			pageRows := conns[offset:end]
			if pageRows == nil {
				pageRows = []collector.ConnectionEntry{}
			}
			writeJSON(w, map[string]interface{}{
				"source": "conntrack", "connections": pageRows,
				"summary":    summarizeConnectionEntries(conns),
				"pagination": pagination(total, limit, offset),
			})
			return
		}
		conns, page, summary := agg.ConnectionEntries(120, limit, offset, filters)
		writeJSON(w, map[string]interface{}{
			"source": "capture", "connections": conns,
			"summary":    summary,
			"pagination": page,
		})
	})

	mux.HandleFunc("/api/diagnostics", func(w http.ResponseWriter, r *http.Request) {
		dcap, dcache := agg.Diagnostics()
		dcap.Enabled = len(captureList) > 0
		dcap.Interfaces = captureList
		dcap.MaxEventsPerSecond = maxEPS
		dcap.SampleRate = bsr
		dcap.DynamicSample = ds
		dcap.MaxSampleRate = msr
		var ms runtime.MemStats
		runtime.ReadMemStats(&ms)
		writeJSON(w, collector.DiagnosticsResponse{
			Timestamp: float64(time.Now().UnixNano()) / 1e9,
			Capture:   dcap,
			Caches:    dcache,
			Conntrack: ctReader.ReadSummary(cml, 1*time.Second),
			Memory:    collector.MemoryDiagnostics{RSSBytes: int64(ms.Alloc), VMSBytes: int64(ms.Sys)},
		})
	})

	mux.HandleFunc("/api/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]interface{}{
			"ok":                true,
			"captureReady":      captureEng.Ready(),
			"captureInterfaces": captureList,
			"timestamp":         time.Now().Unix(),
		})
	})

	mux.HandleFunc("/api/stage/start", func(w http.ResponseWriter, r *http.Request) {
		agg.StartStage()
		writeJSON(w, map[string]interface{}{"ok": true})
	})

	mux.HandleFunc("/api/stage/stop", func(w http.ResponseWriter, r *http.Request) {
		agg.StopStage()
		writeJSON(w, map[string]interface{}{"ok": true})
	})

	mux.HandleFunc("/api/stage/reset", func(w http.ResponseWriter, r *http.Request) {
		agg.ResetStage(true)
		writeJSON(w, map[string]interface{}{"ok": true})
	})

	mux.HandleFunc("/api/stage/info", func(w http.ResponseWriter, r *http.Request) {
		active, startedAt, stageData := agg.StageSnapshot()
		writeJSON(w, map[string]interface{}{
			"active":    active,
			"startedAt": startedAt,
			"stage":     stageData,
		})
	})

	log.Fatal(http.ListenAndServe(listenAddr, mux))
}

func writeJSON(w http.ResponseWriter, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

func defaultQuery(r *http.Request, key, fallback string) string {
	value := r.URL.Query().Get(key)
	if value == "" {
		return fallback
	}
	return value
}

func queryInt(r *http.Request, key string, fallback, minVal, maxVal int) int {
	value := r.URL.Query().Get(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	if parsed < minVal {
		return minVal
	}
	if parsed > maxVal {
		return maxVal
	}
	return parsed
}

func pagination(total, limit, offset int) collector.ConnectionPage {
	if limit <= 0 {
		limit = 120
	}
	pages := 1
	if total > 0 {
		pages = (total + limit - 1) / limit
	}
	return collector.ConnectionPage{Total: total, Limit: limit, Offset: offset, Page: offset/limit + 1, Pages: pages}
}

func summarizeConnectionEntries(rows []collector.ConnectionEntry) collector.ConnectionSummary {
	summary := collector.ConnectionSummary{}
	for _, row := range rows {
		summary.Total++
		if row.Scope == "lan" {
			summary.LAN++
		} else {
			summary.WAN++
		}
	}
	return summary
}

func envInt(key string, defaultVal int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return defaultVal
}

func envFloat(key string, defaultVal float64) float64 {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.ParseFloat(v, 64); err == nil {
			return n
		}
	}
	return defaultVal
}

func envBool(key string, defaultVal bool) bool {
	v := strings.ToLower(os.Getenv(key))
	return v == "true" || v == "1" || v == "yes" || v == "" && defaultVal
}

func envStr(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
