package collector

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

type SocketMapper struct {
	mu       sync.RWMutex
	sockMap  map[string]ProcInfo
	procRoot string
}

func NewSocketMapper() *SocketMapper {
	root := "/proc"
	if _, err := os.Stat("/host/proc"); err == nil {
		root = "/host/proc"
	}
	return &SocketMapper{procRoot: root}
}

func (sm *SocketMapper) Refresh(timeout time.Duration, maxFDLinks, maxNetLines int) {
	inodeToProc := sm.scanFDs(timeout, maxFDLinks)
	sockets := sm.scanNet(timeout, maxNetLines)

	sm.mu.Lock()
	defer sm.mu.Unlock()
	sm.sockMap = make(map[string]ProcInfo)

	for sk, inode := range sockets {
		proc, ok := inodeToProc[inode]
		if !ok {
			continue
		}
		proto, lip, rip, lp, rp := sk.proto, sk.localIP, sk.remoteIP, sk.localPort, sk.remotePort
		k := fmt.Sprintf("%s|%s|%s|%d|%d", proto, lip, rip, lp, rp)
		sm.sockMap[k] = proc
		sm.sockMap[fmt.Sprintf("%s|0.0.0.0|%s|%d|%d", proto, rip, lp, rp)] = proc
		sm.sockMap[fmt.Sprintf("%s|::|%s|%d|%d", proto, rip, lp, rp)] = proc
		sm.sockMap[fmt.Sprintf("%s|%s|0.0.0.0|%d|0", proto, lip, lp)] = proc
		sm.sockMap[fmt.Sprintf("%s|%s|::|%d|0", proto, lip, lp)] = proc
	}
}

func (sm *SocketMapper) GetMap() map[string]ProcInfo {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	result := make(map[string]ProcInfo, len(sm.sockMap))
	for k, v := range sm.sockMap {
		result[k] = v
	}
	return result
}

type sockKey struct {
	proto                 string
	localIP, remoteIP     string
	localPort, remotePort int
}

func (sm *SocketMapper) scanFDs(timeout time.Duration, maxLinks int) map[int]ProcInfo {
	result := make(map[int]ProcInfo)
	entries, err := os.ReadDir(sm.procRoot)
	if err != nil {
		return result
	}
	deadline := time.Now().Add(timeout)
	scanned := 0
	for _, entry := range entries {
		if time.Now().After(deadline) || scanned > maxLinks {
			break
		}
		if !entry.IsDir() {
			continue
		}
		pid, err := strconv.Atoi(entry.Name())
		if err != nil {
			continue
		}
		pidDir := sm.procRoot + "/" + entry.Name()
		proc := ProcInfo{
			PID:     pid,
			Name:    readFirstLine(pidDir + "/comm"),
			Cmdline: readCmdline(pidDir + "/cmdline"),
		}
		fdDir := pidDir + "/fd"
		fds, err := os.ReadDir(fdDir)
		if err != nil {
			continue
		}
		for _, fd := range fds {
			scanned++
			if time.Now().After(deadline) || scanned > maxLinks {
				break
			}
			link, err := os.Readlink(fdDir + "/" + fd.Name())
			if err != nil {
				continue
			}
			if strings.HasPrefix(link, "socket:[") && strings.HasSuffix(link, "]") {
				inodeStr := link[8 : len(link)-1]
				if inode, err := strconv.Atoi(inodeStr); err == nil && inode > 0 {
					result[inode] = proc
				}
			}
		}
	}
	return result
}

func (sm *SocketMapper) scanNet(timeout time.Duration, maxLines int) map[sockKey]int {
	result := make(map[sockKey]int)
	for _, prefix := range []string{"/proc/net", "/host/proc/net"} {
		for _, file := range []string{"tcp", "udp", "tcp6", "udp6"} {
			fullPath := prefix + "/" + file
			for k, v := range parseNetFile(fullPath, file, timeout, maxLines) {
				result[k] = v
			}
		}
		if len(result) > 0 {
			break
		}
	}
	return result
}

func parseNetFile(path, name string, timeout time.Duration, maxLines int) map[sockKey]int {
	result := make(map[sockKey]int)
	f, err := os.Open(path)
	if err != nil {
		return result
	}
	defer f.Close()

	proto := "tcp"
	if strings.Contains(name, "udp") {
		proto = "udp"
	}
	deadline := time.Now().Add(timeout)
	scanner := bufio.NewScanner(f)
	scanner.Scan() // skip header
	for scanner.Scan() {
		if time.Now().After(deadline) || len(result) >= maxLines {
			break
		}
		parts := strings.Fields(scanner.Text())
		if len(parts) < 10 {
			continue
		}
		localIP, localPort := decodeHexAddr(parts[1])
		remoteIP, remotePort := decodeHexAddr(parts[2])
		inode, err := strconv.Atoi(parts[9])
		if err != nil || inode <= 0 {
			continue
		}
		result[sockKey{proto, localIP, remoteIP, localPort, remotePort}] = inode
	}
	return result
}

func decodeHexAddr(hex string) (string, int) {
	parts := strings.Split(hex, ":")
	if len(parts) < 2 {
		return "", 0
	}
	port, _ := strconv.ParseInt(parts[1], 16, 64)
	if len(parts[0]) == 8 {
		v, _ := strconv.ParseUint(parts[0], 16, 64)
		return net.IPv4(byte(v), byte(v>>8), byte(v>>16), byte(v>>24)).String(), int(port)
	}
	// IPv6 — build from groups of 8 hex chars
	raw := parts[0]
	ip := make(net.IP, net.IPv6len)
	for i := 0; i < 4; i++ {
		if i*8+8 > len(raw) {
			break
		}
		val, _ := strconv.ParseUint(raw[i*8:(i+1)*8], 16, 32)
		ip[i*4] = byte(val >> 24)
		ip[i*4+1] = byte(val >> 16)
		ip[i*4+2] = byte(val >> 8)
		ip[i*4+3] = byte(val)
	}
	return ip.String(), int(port)
}

func GetLocalAddresses() map[string]bool {
	addrs := make(map[string]bool)
	ifaces, err := net.Interfaces()
	if err != nil {
		return addrs
	}
	for _, iface := range ifaces {
		addrList, _ := iface.Addrs()
		for _, addr := range addrList {
			s := addr.String()
			if idx := strings.Index(s, "/"); idx >= 0 {
				s = s[:idx]
			}
			if idx := strings.Index(s, "%"); idx >= 0 {
				s = s[:idx]
			}
			if net.ParseIP(s) != nil {
				addrs[s] = true
			}
		}
	}
	return addrs
}

func GetInterfaceDetails(captured map[string]bool) map[string]InterfaceDetail {
	details := make(map[string]InterfaceDetail)
	ifaces, err := net.Interfaces()
	if err != nil {
		return details
	}
	defaultRoutes := getDefaultRoutes()
	for _, iface := range ifaces {
		d := classifyIface(iface, defaultRoutes)
		d.Captured = captured[iface.Name]
		d.Name = iface.Name
		d.Mac = iface.HardwareAddr.String()
		d.Mtu = iface.MTU
		d.IsUp = iface.Flags&net.FlagUp != 0
		addrs, _ := iface.Addrs()
		for _, addr := range addrs {
			s := addr.String()
			if idx := strings.Index(s, "/"); idx >= 0 {
				s = s[:idx]
			}
			if idx := strings.Index(s, "%"); idx >= 0 {
				s = s[:idx]
			}
			if net.ParseIP(s) != nil {
				d.IPs = append(d.IPs, s)
			}
		}
		details[iface.Name] = d
	}
	return details
}

func classifyIface(iface net.Interface, defaultRoutes map[string]bool) InterfaceDetail {
	lowered := strings.ToLower(iface.Name)
	isDefault := defaultRoutes[iface.Name]
	d := InterfaceDetail{Role: "其他接口", Note: "系统网络接口", Virtual: true, Priority: 80}

	switch {
	case lowered == "lo":
		d.Role, d.Note, d.Priority = "回环接口", "本机内部通信", 100
	case strings.HasPrefix(lowered, "veth"):
		d.Role, d.Note, d.Priority = "容器 veth", "容器虚拟链路", 70
	case lowered == "docker0":
		d.Role, d.Note, d.Priority = "Docker 默认网桥", "Docker 容器默认桥接网络", 55
	case strings.HasPrefix(lowered, "br-"):
		d.Role, d.Note, d.Priority = "Docker 自定义网桥", "Docker Compose 或自定义容器网络", 58
	case strings.HasPrefix(lowered, "virbr"):
		d.Role, d.Note, d.Priority = "虚拟化网桥", "虚拟机或系统虚拟网络", 60
	case strings.HasPrefix(lowered, "ifb"):
		d.Role, d.Note, d.Priority = "流控镜像接口", "Linux IFB 流量整形接口", 65
	case strings.HasPrefix(lowered, "bond"):
		d.Role, d.Note, d.Virtual, d.Priority = "链路聚合", "多网口聚合接口", false, 15
	case isPhysical(lowered):
		d.Role, d.Note, d.Virtual, d.Priority = "物理网卡", "NAS 对外物理网络接口", false, 10
	}
	if isDefault {
		d.Role += " / 默认路由"
		if d.Priority > 5 {
			d.Priority = 5
		}
	}
	d.DefaultRoute = isDefault
	d.CaptureRecommended = d.IsUp && lowered != "lo" && (!d.Virtual || isDefault)
	return d
}

func isPhysical(name string) bool {
	for _, p := range []string{"eth", "enp", "eno", "ens", "em", "p", "bond", "wlan"} {
		if strings.HasPrefix(name, p) {
			return true
		}
	}
	return false
}

func getDefaultRoutes() map[string]bool {
	routes := make(map[string]bool)
	f, err := os.Open("/proc/net/route")
	if err != nil {
		return routes
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	scanner.Scan()
	for scanner.Scan() {
		parts := strings.Fields(scanner.Text())
		if len(parts) >= 2 && parts[1] == "00000000" {
			routes[parts[0]] = true
		}
	}
	return routes
}

func GetSystemIO() map[string]SystemCounters {
	io := make(map[string]SystemCounters)
	f, err := os.Open("/proc/net/dev")
	if err != nil {
		return io
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	scanner.Scan() // skip header 1
	scanner.Scan() // skip header 2
	for scanner.Scan() {
		line := scanner.Text()
		parts := strings.Fields(line)
		if len(parts) < 10 {
			continue
		}
		name := strings.TrimSuffix(parts[0], ":")
		rxBytes, _ := strconv.ParseInt(parts[1], 10, 64)
		rxPkts, _ := strconv.ParseInt(parts[2], 10, 64)
		txBytes, _ := strconv.ParseInt(parts[9], 10, 64)
		txPkts, _ := strconv.ParseInt(parts[10], 10, 64)
		io[name] = SystemCounters{RxBytes: rxBytes, RxPackets: rxPkts, TxBytes: txBytes, TxPackets: txPkts}
	}
	return io
}

func DetermineCaptureInterfaces(details map[string]InterfaceDetail, requested string) []string {
	if requested == "" {
		var selected []string
		for name, d := range details {
			if d.IsUp && d.CaptureRecommended && !strings.HasPrefix(strings.ToLower(name), "veth") {
				selected = append(selected, name)
			}
		}
		if len(selected) > 0 {
			return selected
		}
		for name, d := range details {
			if d.IsUp && name != "lo" {
				return []string{name}
			}
		}
		return nil
	}
	if requested == "all" {
		var all []string
		for name, d := range details {
			if d.IsUp && name != "lo" {
				all = append(all, name)
			}
		}
		return all
	}
	var result []string
	for _, p := range strings.Split(requested, ",") {
		p = strings.TrimSpace(p)
		if p != "" {
			result = append(result, p)
		}
	}
	return result
}

type ConntrackReader struct {
	paths            []string
	mode             string
	tcpStates        map[string]bool
	udpAssured       bool
	includeUnreplied bool
	minTimeout       int
}

func NewConntrackReader(mode string, tcpStates []string, udpAssured, includeUnreplied bool, minTimeout int) *ConntrackReader {
	states := make(map[string]bool)
	for _, s := range tcpStates {
		states[strings.ToUpper(strings.TrimSpace(s))] = true
	}
	return &ConntrackReader{
		paths: []string{
			"/host/proc/net/nf_conntrack", "/proc/net/nf_conntrack",
			"/host/proc/net/ip_conntrack", "/proc/net/ip_conntrack",
		},
		mode: mode, tcpStates: states, udpAssured: udpAssured,
		includeUnreplied: includeUnreplied, minTimeout: minTimeout,
	}
}

func (cr *ConntrackReader) FindPath() string {
	for _, p := range cr.paths {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

func (cr *ConntrackReader) ReadSummary(maxLines int, timeBudget time.Duration) ConntrackSummary {
	path := cr.FindPath()
	if path == "" {
		return ConntrackSummary{Available: false, Source: "capture", Mode: cr.mode}
	}
	f, err := os.Open(path)
	if err != nil {
		return ConntrackSummary{Available: false, Source: "capture", Mode: cr.mode}
	}
	defer f.Close()

	s := ConntrackSummary{Available: true, Source: "conntrack", Mode: cr.mode}
	deadline := time.Now().Add(timeBudget)
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		s.RawTotal++
		if s.RawTotal > maxLines || time.Now().After(deadline) {
			s.Truncated = true
			break
		}
		e := cr.parseLine(scanner.Text())
		if e == nil || !cr.isActive(e) {
			continue
		}
		s.Total++
		if cr.getScope(e) == "lan" {
			s.LAN++
		} else {
			s.WAN++
		}
	}
	s.ScannedLines = s.RawTotal
	return s
}

func (cr *ConntrackReader) ReadConnections(maxLines int, timeBudget time.Duration, filters ConnectionFilters) []ConnectionEntry {
	path := cr.FindPath()
	if path == "" {
		return nil
	}
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	var conns []ConnectionEntry
	deadline := time.Now().Add(timeBudget)
	scanned := 0
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		scanned++
		if scanned > maxLines || time.Now().After(deadline) {
			break
		}
		e := cr.parseLine(scanner.Text())
		if e == nil || !cr.isActive(e) {
			continue
		}
		scope := cr.getScope(e)
		srcText := fmt.Sprintf("%s:%d", e.replySrc, e.replySport)
		dstText := fmt.Sprintf("%s:%d", e.replyDst, e.replyDport)
		if e.replySrc == "" {
			srcText = fmt.Sprintf("%s:%d", e.src, e.sport)
			dstText = fmt.Sprintf("%s:%d", e.dst, e.dport)
		}
		total := e.rxBytes + e.txBytes
		item := ConnectionEntry{
			Iface: "conntrack", Scope: scope, Proto: e.proto,
			Source: srcText, Dest: dstText,
			RxBytes: e.rxBytes, TxBytes: e.txBytes, TotalBytes: total,
			Duration: float64(e.timeout),
			Process:  map[string]interface{}{"pid": nil, "name": "conntrack", "cmdline": ""},
		}
		item.Direction = "rx"
		if item.TxBytes >= item.RxBytes {
			item.Direction = "tx"
		}
		if !connectionMatches(item, filters) {
			continue
		}
		conns = append(conns, item)
	}
	return conns
}

type ctEntry struct {
	proto, state                         string
	flags                                map[string]bool
	timeout                              int
	src, dst, replySrc, replyDst         string
	sport, dport, replySport, replyDport int
	txBytes, rxBytes, txPkts, rxPkts     int64
	addresses                            []string
}

func (cr *ConntrackReader) parseLine(line string) *ctEntry {
	parts := strings.Fields(line)
	pi := -1
	for i, p := range parts {
		if strings.ToLower(p) == "tcp" || strings.ToLower(p) == "udp" {
			pi = i
			break
		}
	}
	if pi < 0 {
		return nil
	}
	e := &ctEntry{proto: strings.ToLower(parts[pi]), flags: make(map[string]bool)}
	for _, v := range parts[pi+1:] {
		if strings.Contains(v, "=") || strings.HasPrefix(v, "[") {
			break
		}
		if n, err := strconv.Atoi(v); err == nil {
			e.timeout = n
		}
	}
	for _, v := range parts[pi+1:] {
		if strings.Contains(v, "=") {
			break
		}
		cleaned := strings.Trim(v, "[]")
		if _, ok := ctKnownStates[cleaned]; ok {
			e.state = cleaned
			break
		}
	}
	for _, v := range parts {
		if strings.HasPrefix(v, "[") && strings.HasSuffix(v, "]") {
			e.flags[strings.Trim(v, "[]")] = true
		}
	}
	for _, part := range parts {
		if !strings.Contains(part, "=") {
			continue
		}
		kv := strings.SplitN(part, "=", 2)
		key, val := kv[0], kv[1]
		switch key {
		case "src":
			if e.src == "" {
				e.src = val
			} else {
				e.replySrc = val
			}
		case "dst":
			if e.dst == "" {
				e.dst = val
			} else {
				e.replyDst = val
			}
		case "sport":
			if e.sport == 0 {
				e.sport, _ = strconv.Atoi(val)
			} else {
				e.replySport, _ = strconv.Atoi(val)
			}
		case "dport":
			if e.dport == 0 {
				e.dport, _ = strconv.Atoi(val)
			} else {
				e.replyDport, _ = strconv.Atoi(val)
			}
		case "bytes":
			if e.txBytes == 0 {
				e.txBytes, _ = strconv.ParseInt(val, 10, 64)
			} else {
				e.rxBytes, _ = strconv.ParseInt(val, 10, 64)
			}
		case "packets":
			if e.txPkts == 0 {
				e.txPkts, _ = strconv.ParseInt(val, 10, 64)
			} else {
				e.rxPkts, _ = strconv.ParseInt(val, 10, 64)
			}
		}
	}
	for _, a := range []string{e.src, e.dst, e.replySrc, e.replyDst} {
		if a != "" {
			e.addresses = append(e.addresses, a)
		}
	}
	return e
}

var ctKnownStates = map[string]bool{
	"SYN_SENT": true, "SYN_RECV": true, "ESTABLISHED": true,
	"FIN_WAIT": true, "TIME_WAIT": true, "CLOSE": true,
	"CLOSE_WAIT": true, "LAST_ACK": true, "LISTEN": true,
}

func (cr *ConntrackReader) isActive(e *ctEntry) bool {
	if cr.mode == "raw" {
		return true
	}
	if e.timeout < cr.minTimeout {
		return false
	}
	if e.flags["UNREPLIED"] && !cr.includeUnreplied {
		return false
	}
	if e.proto == "tcp" {
		return cr.tcpStates[e.state]
	}
	if e.proto == "udp" {
		if cr.udpAssured {
			return e.flags["ASSURED"]
		}
		return true
	}
	return false
}

func (cr *ConntrackReader) getScope(e *ctEntry) string {
	for _, a := range e.addresses {
		ip := net.ParseIP(a)
		if ip != nil && !IsPrivateIP(ip) {
			return "wan"
		}
	}
	return "lan"
}

func readFirstLine(path string) string {
	f, err := os.Open(path)
	if err != nil {
		return "unknown"
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	if scanner.Scan() {
		return strings.TrimSpace(scanner.Text())
	}
	return "unknown"
}

func readCmdline(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.ReplaceAll(string(data), "\x00", " ")
}
