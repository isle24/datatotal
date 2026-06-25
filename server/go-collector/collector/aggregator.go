package collector

import (
	"encoding/json"
	"sort"
	"strings"
	"sync"
	"time"
)

type Aggregator struct {
	mu sync.Mutex

	IfaceTotals           map[string]map[string]*Counter
	ProcessTotals         map[string]*Counter
	PortTotals            map[string]*Counter
	ConnTotals            map[string]*Counter
	ProcessRecent         map[int64]map[string]*Counter
	StageTotals           map[string]map[string]*Counter
	CalibratedIfaceTotals map[string]map[string]*Counter
	CalibratedStageTotals map[string]map[string]*Counter

	StageStartedAt float64
	StagePaused    bool

	SeenEvents          int64
	RecordedEvents      int64
	DroppedEvents       int64
	SampledEvents       int64
	WeightedBytes       int64
	CaptureWindowSecond int64
	CaptureWindowEvents int64
}

func NewAggregator() *Aggregator {
	return &Aggregator{
		IfaceTotals:           make(map[string]map[string]*Counter),
		ProcessTotals:         make(map[string]*Counter),
		PortTotals:            make(map[string]*Counter),
		ConnTotals:            make(map[string]*Counter),
		ProcessRecent:         make(map[int64]map[string]*Counter),
		StageTotals:           make(map[string]map[string]*Counter),
		CalibratedIfaceTotals: make(map[string]map[string]*Counter),
		CalibratedStageTotals: make(map[string]map[string]*Counter),
	}
}

func (a *Aggregator) getOrCreateCounter(m map[string]*Counter, key string) *Counter {
	c, ok := m[key]
	if !ok {
		c = &Counter{}
		m[key] = c
	}
	return c
}

func (a *Aggregator) Record(event PacketEvent) {
	a.mu.Lock()
	defer a.mu.Unlock()

	weight := int64(event.Weight)
	if weight < 1 {
		weight = 1
	}
	weightedSize := int64(event.Size) * weight

	// iface totals
	if _, ok := a.IfaceTotals[event.Iface]; !ok {
		a.IfaceTotals[event.Iface] = make(map[string]*Counter)
	}
	c := a.getOrCreateCounter(a.IfaceTotals[event.Iface], event.Scope)
	c.Add(event.Direction, weightedSize, weight)

	// process totals
	procKey := ProcessKeyFor(ProcInfo{
		PID:     getIntVal(event.Process, "pid"),
		Name:    getStrVal(event.Process, "name"),
		Cmdline: getStrVal(event.Process, "cmdline"),
	}, containerFromMap(event.Process), false)
	pc := a.getOrCreateCounter(a.ProcessTotals, procKey)
	pc.Add(event.Direction, weightedSize, weight)

	// port totals
	portKey := event.Proto + ":" + itoa(event.Sport) + "->" + itoa(event.Dport)
	ppc := a.getOrCreateCounter(a.PortTotals, portKey)
	ppc.Add(event.Direction, weightedSize, weight)

	// connection totals
	connProcKey := ProcessKeyFor(ProcInfo{
		PID:     getIntVal(event.Process, "pid"),
		Name:    getStrVal(event.Process, "name"),
		Cmdline: getStrVal(event.Process, "cmdline"),
	}, containerFromMap(event.Process), true)
	connKey := event.Iface + "|" + event.Scope + "|" + event.Proto + "|" +
		event.Src + ":" + itoa(event.Sport) + "|" +
		event.Dst + ":" + itoa(event.Dport) + "|" + connProcKey
	cc := a.getOrCreateCounter(a.ConnTotals, connKey)
	cc.Add(event.Direction, weightedSize, weight)

	// process recent
	sec := event.Timestamp / 1000
	if _, ok := a.ProcessRecent[sec]; !ok {
		a.ProcessRecent[sec] = make(map[string]*Counter)
	}
	rpc := a.getOrCreateCounter(a.ProcessRecent[sec], procKey)
	rpc.Add(event.Direction, weightedSize, weight)

	a.RecordedEvents++
	if weight > 1 {
		a.WeightedBytes += weightedSize - int64(event.Size)
	}

	// stage totals
	if a.StageStartedAt > 0 && !a.StagePaused {
		if _, ok := a.StageTotals[event.Iface]; !ok {
			a.StageTotals[event.Iface] = make(map[string]*Counter)
		}
		sc := a.getOrCreateCounter(a.StageTotals[event.Iface], event.Scope)
		sc.Add(event.Direction, weightedSize, weight)
	}
}

func (a *Aggregator) PacketWeight(maxEPS, baseRate, maxRate int, dynamic bool) int {
	a.mu.Lock()
	defer a.mu.Unlock()

	a.SeenEvents++
	nowSec := time.Now().Unix()
	if nowSec != a.CaptureWindowSecond {
		a.CaptureWindowSecond = nowSec
		a.CaptureWindowEvents = 0
	}
	a.CaptureWindowEvents++

	if baseRate < 1 {
		baseRate = 1
	}
	dynRate := 1
	if dynamic && maxEPS > 0 && a.CaptureWindowEvents > int64(maxEPS) {
		dynRate = int(a.CaptureWindowEvents/int64(maxEPS)) + 1
		if maxRate > 0 && dynRate > maxRate {
			dynRate = maxRate
		}
	}
	sampleRate := baseRate
	if dynRate > sampleRate {
		sampleRate = dynRate
	}
	if sampleRate > 1 && a.SeenEvents%int64(sampleRate) != 0 {
		a.DroppedEvents++
		return 0
	}
	if sampleRate > 1 {
		a.SampledEvents++
	}
	return sampleRate
}

func (a *Aggregator) StartStage() {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.StageStartedAt = float64(time.Now().UnixNano()) / 1e9
	a.StageTotals = make(map[string]map[string]*Counter)
	a.CalibratedStageTotals = make(map[string]map[string]*Counter)
	a.StagePaused = false
}

func (a *Aggregator) StopStage() {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.StagePaused = true
}

func (a *Aggregator) ResetStage(active bool) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if active {
		a.StageStartedAt = float64(time.Now().UnixNano()) / 1e9
	} else {
		a.StageStartedAt = 0
	}
	a.StageTotals = make(map[string]map[string]*Counter)
	a.CalibratedStageTotals = make(map[string]map[string]*Counter)
	a.StagePaused = false
}

func (a *Aggregator) StageSnapshot() (bool, float64, map[string]map[string]CounterData) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.StageStartedAt == 0 {
		return false, 0, nil
	}
	active := !a.StagePaused
	result := make(map[string]map[string]CounterData)
	for iface, scopes := range a.StageTotals {
		result[iface] = make(map[string]CounterData)
		for scope, counter := range scopes {
			result[iface][scope] = counter.Snapshot()
		}
	}
	for iface, scopes := range a.CalibratedStageTotals {
		if _, ok := result[iface]; !ok {
			result[iface] = make(map[string]CounterData)
		}
		for scope, counter := range scopes {
			cd := counter.Snapshot()
			if existing, ok := result[iface][scope]; ok {
				cd.RxBytes += existing.RxBytes
				cd.TxBytes += existing.TxBytes
				cd.RxPackets += existing.RxPackets
				cd.TxPackets += existing.TxPackets
			}
			result[iface][scope] = cd
		}
	}
	return active, a.StageStartedAt, result
}

func (a *Aggregator) TrimCaches(maxConn, maxProc, maxPort int, processRecentSec int64) {
	a.mu.Lock()
	defer a.mu.Unlock()

	trimByLastSeen(a.ConnTotals, maxConn)
	trimByLastSeen(a.ProcessTotals, maxProc)
	trimByLastSeen(a.PortTotals, maxPort)

	cutoff := time.Now().Unix() - processRecentSec
	for bucket := range a.ProcessRecent {
		if bucket < cutoff {
			delete(a.ProcessRecent, bucket)
		}
	}
}

func (a *Aggregator) PruneConnections(retentionSec int64) {
	a.mu.Lock()
	defer a.mu.Unlock()
	cutoff := time.Now().UnixMilli() - retentionSec*1000
	for key, c := range a.ConnTotals {
		if c.LastSeen < cutoff {
			delete(a.ConnTotals, key)
		}
	}
}

func (a *Aggregator) SnapshotInterfaces(sysIO map[string]SystemCounters, details map[string]InterfaceDetail) map[string]InterfaceState {
	a.mu.Lock()
	defer a.mu.Unlock()

	result := make(map[string]InterfaceState)
	captureSet := make(map[string]bool)
	for _, d := range details {
		if d.Captured {
			captureSet[d.Name] = true
		}
	}

	for name, io := range sysIO {
		detail := details[name]
		detail.Name = name
		detail.Captured = captureSet[name]

		scopes := make(map[string]CounterData)
		if ifaceScopes, ok := a.IfaceTotals[name]; ok {
			for scope, counter := range ifaceScopes {
				scopes[scope] = counter.Snapshot()
			}
		}
		if calScopes, ok := a.CalibratedIfaceTotals[name]; ok {
			for scope, counter := range calScopes {
				cd := counter.Snapshot()
				if existing, eok := scopes[scope]; eok {
					cd.RxBytes += existing.RxBytes
					cd.TxBytes += existing.TxBytes
					cd.RxPackets += existing.RxPackets
					cd.TxPackets += existing.TxPackets
				}
				scopes[scope] = cd
			}
		}
		result[name] = InterfaceState{Detail: detail, Scopes: scopes, System: io}
	}

	for iface, ifaceScopes := range a.IfaceTotals {
		if _, ok := result[iface]; ok {
			continue
		}
		detail := details[iface]
		detail.Name = iface
		detail.Captured = captureSet[iface]
		scopes := make(map[string]CounterData)
		for scope, counter := range ifaceScopes {
			scopes[scope] = counter.Snapshot()
		}
		result[iface] = InterfaceState{Detail: detail, Scopes: scopes, System: SystemCounters{}}
	}
	return result
}

func (a *Aggregator) ConnectionCounts(activeSec int64, ifaceNames map[string]bool) ConnectionSummary {
	a.mu.Lock()
	defer a.mu.Unlock()

	cutoff := time.Now().UnixMilli() - int64(activeSec)*1000
	summary := ConnectionSummary{}

	for key, counter := range a.ConnTotals {
		if counter.LastSeen < cutoff {
			continue
		}
		if len(ifaceNames) > 0 {
			iface := parseConnIface(key)
			if iface != "" && !ifaceNames[iface] {
				continue
			}
		}
		summary.Total++
		if parseConnScope(key) == "wan" {
			summary.WAN++
		} else {
			summary.LAN++
		}
	}
	return summary
}

func (a *Aggregator) DiffRates(prev, current map[string]InterfaceState, elapsed float64) map[string]InterfaceRate {
	rates := make(map[string]InterfaceRate)
	for name, curItem := range current {
		prevItem, ok := prev[name]
		scopes := make(map[string]ScopeRate)
		for scope, curCounter := range curItem.Scopes {
			sr := ScopeRate{}
			if ok {
				if prevCounter, pok := prevItem.Scopes[scope]; pok {
					sr.RxBps = float64(max64(0, curCounter.RxBytes-prevCounter.RxBytes)) / elapsed
					sr.TxBps = float64(max64(0, curCounter.TxBytes-prevCounter.TxBytes)) / elapsed
				}
			} else {
				sr.RxBps = float64(max64(0, curCounter.RxBytes)) / elapsed
				sr.TxBps = float64(max64(0, curCounter.TxBytes)) / elapsed
			}
			scopes[scope] = sr
		}
		systemRxBps, systemTxBps := 0.0, 0.0
		if ok {
			systemRxBps = float64(max64(0, curItem.System.RxBytes-prevItem.System.RxBytes)) / elapsed
			systemTxBps = float64(max64(0, curItem.System.TxBytes-prevItem.System.TxBytes)) / elapsed
		}
		rates[name] = InterfaceRate{SystemRxBps: systemRxBps, SystemTxBps: systemTxBps, Scopes: scopes}
	}
	return rates
}

func (a *Aggregator) ProcessRankFromEvents(startSec, endSec int64, limit int) []ProcessEntry {
	a.mu.Lock()
	defer a.mu.Unlock()

	merged := make(map[string]*Counter)
	for bucket, processes := range a.ProcessRecent {
		if bucket >= startSec && bucket <= endSec {
			for key, counter := range processes {
				c := merged[key]
				if c == nil {
					c = &Counter{}
					merged[key] = c
				}
				c.RxBytes += counter.RxBytes
				c.TxBytes += counter.TxBytes
				c.RxPackets += counter.RxPackets
				c.TxPackets += counter.TxPackets
				if c.FirstSeen == 0 || counter.FirstSeen < c.FirstSeen {
					c.FirstSeen = counter.FirstSeen
				}
				if counter.LastSeen > c.LastSeen {
					c.LastSeen = counter.LastSeen
				}
			}
		}
	}

	entries := make([]ProcessEntry, 0)
	for key, counter := range merged {
		proc := ParseProcessKey(key)
		cd := counter.Snapshot()
		entries = append(entries, ProcessEntry{
			PID:       proc.PID,
			Name:      proc.Name,
			Cmdline:   proc.Cmdline,
			Container: proc.Container,
			CounterData: CounterData{
				RxBytes: cd.RxBytes, TxBytes: cd.TxBytes,
				RxPackets: cd.RxPackets, TxPackets: cd.TxPackets,
				FirstSeen: cd.FirstSeen, LastSeen: cd.LastSeen,
			},
			TotalBytes:      cd.RxBytes + cd.TxBytes,
			DurationSeconds: float64(max64(cd.LastSeen-cd.FirstSeen, 0)) / 1000.0,
		})
	}

	for i := 0; i < len(entries); i++ {
		for j := i + 1; j < len(entries); j++ {
			if entries[j].TotalBytes > entries[i].TotalBytes {
				entries[i], entries[j] = entries[j], entries[i]
			}
		}
	}
	if limit > 0 && len(entries) > limit {
		entries = entries[:limit]
	}
	return entries
}

func (a *Aggregator) Diagnostics() (CaptureDiagnostics, CacheDiagnostics) {
	a.mu.Lock()
	defer a.mu.Unlock()

	recentKeys := 0
	for _, processes := range a.ProcessRecent {
		recentKeys += len(processes)
	}
	return CaptureDiagnostics{
			SeenEvents:     a.SeenEvents,
			RecordedEvents: a.RecordedEvents,
			DroppedEvents:  a.DroppedEvents,
			SampledEvents:  a.SampledEvents,
			WeightedBytes:  a.WeightedBytes,
		}, CacheDiagnostics{
			ConnectionCount:      len(a.ConnTotals),
			ProcessCount:         len(a.ProcessTotals),
			PortCount:            len(a.PortTotals),
			RecentProcessKeys:    recentKeys,
			RecentProcessBuckets: len(a.ProcessRecent),
		}
}

func (a *Aggregator) ConnectionEntries(activeSec, limit, offset int, filters ConnectionFilters) ([]ConnectionEntry, ConnectionPage, ConnectionSummary) {
	a.mu.Lock()
	defer a.mu.Unlock()

	if limit <= 0 {
		limit = 120
	}
	if limit > 300 {
		limit = 300
	}
	if offset < 0 {
		offset = 0
	}
	cutoff := time.Now().UnixMilli() - int64(activeSec)*1000
	entries := make([]ConnectionEntry, 0)
	summary := ConnectionSummary{}
	for key, counter := range a.ConnTotals {
		if counter.LastSeen < cutoff {
			continue
		}
		item := ParseConnKey(key)
		cd := counter.Snapshot()
		item.RxBytes = cd.RxBytes
		item.TxBytes = cd.TxBytes
		item.TotalBytes = cd.RxBytes + cd.TxBytes
		item.RxPackets = cd.RxPackets
		item.TxPackets = cd.TxPackets
		item.FirstSeen = float64(cd.FirstSeen) / 1000.0
		item.LastSeen = float64(cd.LastSeen) / 1000.0
		item.Duration = item.LastSeen - item.FirstSeen
		item.Direction = "rx"
		if item.TxBytes >= item.RxBytes {
			item.Direction = "tx"
		}
		if !connectionMatches(item, filters) {
			continue
		}
		entries = append(entries, item)
		summary.Total++
		if item.Scope == "lan" {
			summary.LAN++
		} else {
			summary.WAN++
		}
	}
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].TotalBytes > entries[j].TotalBytes
	})
	total := len(entries)
	if offset > total {
		offset = total
	}
	end := offset + limit
	if end > total {
		end = total
	}
	pageRows := entries[offset:end]
	if pageRows == nil {
		pageRows = []ConnectionEntry{}
	}
	pages := 1
	if total > 0 {
		pages = (total + limit - 1) / limit
	}
	return pageRows, ConnectionPage{
		Total: total, Limit: limit, Offset: offset,
		Page: (offset / limit) + 1, Pages: pages,
	}, summary
}

func connectionMatches(item ConnectionEntry, filters ConnectionFilters) bool {
	if filters.Iface != "" && filters.Iface != "all" && item.Iface != filters.Iface {
		return false
	}
	if filters.Scope != "" && filters.Scope != "all" && item.Scope != filters.Scope {
		return false
	}
	if filters.Proto != "" && filters.Proto != "all" && item.Proto != filters.Proto {
		return false
	}
	if filters.Direction == "rx" && item.RxBytes <= 0 {
		return false
	}
	if filters.Direction == "tx" && item.TxBytes <= 0 {
		return false
	}
	if filters.MinBytes > 0 && item.TotalBytes < filters.MinBytes {
		return false
	}
	if filters.MinDuration > 0 && int64(item.Duration) < filters.MinDuration {
		return false
	}
	if filters.Owner != "" {
		owner := strings.ToLower(filters.Owner)
		name, _ := item.Process["name"].(string)
		cmdline, _ := item.Process["cmdline"].(string)
		if !strings.Contains(strings.ToLower(name+" "+cmdline), owner) {
			return false
		}
	}
	if filters.Source != "" && !strings.Contains(strings.ToLower(item.Source), strings.ToLower(filters.Source)) {
		return false
	}
	if filters.Dest != "" && !strings.Contains(strings.ToLower(item.Dest), strings.ToLower(filters.Dest)) {
		return false
	}
	return true
}

// ParseConnKey parses a connection store key into a ConnectionEntry (no counter values filled).
func ParseConnKey(key string) ConnectionEntry {
	parts := splitN(key, "|", 6)
	ce := ConnectionEntry{
		Proto: "unknown", Scope: "wan",
		Process: map[string]interface{}{"pid": nil, "name": "unknown", "cmdline": ""},
	}
	if len(parts) >= 5 {
		ce.Iface = parts[0]
		ce.Scope = parts[1]
		ce.Proto = parts[2]
		ce.Source = parts[3]
		ce.Dest = parts[4]
	}
	if len(parts) >= 6 {
		proc := ParseProcessKey(parts[5])
		ce.Process = map[string]interface{}{
			"pid": proc.PID, "name": proc.Name, "cmdline": proc.Cmdline,
			"container": proc.Container,
		}
	}
	return ce
}

// ProcessKeyFor encodes proc info as a base64url key (matches Python format).
func ProcessKeyFor(proc ProcInfo, container ContainerInfo, includeDetail bool) string {
	ci := container
	if !includeDetail {
		ci = ContainerInfo{ID: container.ID, Name: container.Name, Label: container.Label}
	}
	payload, _ := json.Marshal(map[string]interface{}{
		"pid": proc.PID, "name": proc.Name, "cmdline": proc.Cmdline, "container": ci,
	})
	return b64url(payload)
}

// ParseProcessKey decodes a process key back to ProcInfo (matches Python format).
func ParseProcessKey(key string) ProcInfo {
	data, err := b64Decode(key)
	if err != nil {
		parts := splitN(key, "|", 3)
		if len(parts) >= 2 {
			pid, _ := parseInt(parts[0])
			cmd := ""
			if len(parts) >= 3 {
				cmd = parts[2]
			}
			return ProcInfo{PID: pid, Name: parts[1], Cmdline: cmd}
		}
		return ProcInfo{Name: key}
	}
	var parsed map[string]interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		parts := splitN(key, "|", 3)
		if len(parts) >= 2 {
			pid, _ := parseInt(parts[0])
			cmd := ""
			if len(parts) >= 3 {
				cmd = parts[2]
			}
			return ProcInfo{PID: pid, Name: parts[1], Cmdline: cmd}
		}
		return ProcInfo{Name: key}
	}
	ci, _ := parsed["container"].(map[string]interface{})
	container := make(map[string]interface{})
	if ci != nil {
		container = ci
	}
	return ProcInfo{
		PID:       getIntVal(parsed, "pid"),
		Name:      getStrVal(parsed, "name"),
		Cmdline:   getStrVal(parsed, "cmdline"),
		Container: container,
	}
}

func trimByLastSeen(m map[string]*Counter, maxItems int) {
	if maxItems <= 0 || len(m) <= maxItems {
		return
	}
	remove := len(m) - maxItems
	type kv struct {
		key string
		ts  int64
	}
	items := make([]kv, 0, len(m))
	for key, c := range m {
		items = append(items, kv{key, c.LastSeen})
	}
	for i := 0; i < remove; i++ {
		minIdx := i
		for j := i + 1; j < len(items); j++ {
			if items[j].ts < items[minIdx].ts {
				minIdx = j
			}
		}
		items[i], items[minIdx] = items[minIdx], items[i]
		delete(m, items[i].key)
	}
}

func parseConnIface(key string) string {
	for i := 0; i < len(key); i++ {
		if key[i] == '|' {
			return key[:i]
		}
	}
	return ""
}

func parseConnScope(key string) string {
	idx1 := -1
	for i := 0; i < len(key); i++ {
		if key[i] == '|' {
			if idx1 < 0 {
				idx1 = i
			} else {
				return key[idx1+1 : i]
			}
		}
	}
	return "wan"
}

func getIntVal(m map[string]interface{}, key string) int {
	if m == nil {
		return 0
	}
	v, _ := m[key]
	switch val := v.(type) {
	case float64:
		return int(val)
	case int:
		return val
	case int64:
		return int(val)
	}
	return 0
}

func getStrVal(m map[string]interface{}, key string) string {
	if m == nil {
		return ""
	}
	v, _ := m[key]
	s, _ := v.(string)
	return s
}

func containerFromMap(proc map[string]interface{}) ContainerInfo {
	if proc == nil {
		return ContainerInfo{}
	}
	ci, _ := proc["container"].(map[string]interface{})
	if ci == nil {
		return ContainerInfo{}
	}
	return ContainerInfo{
		ID:       getStrVal(ci, "id"),
		Name:     getStrVal(ci, "name"),
		Image:    getStrVal(ci, "image"),
		Label:    getStrVal(ci, "label"),
		LabelKey: getStrVal(ci, "labelKey"),
		HostPort: getIntVal(ci, "hostPort"),
		Proto:    getStrVal(ci, "proto"),
	}
}
