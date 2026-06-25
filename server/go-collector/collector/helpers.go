package collector

import (
	"encoding/base64"
	"strconv"
	"strings"
)

func b64url(data []byte) string {
	return base64.RawURLEncoding.EncodeToString(data)
}

func b64Decode(s string) ([]byte, error) {
	switch len(s) % 4 {
	case 2:
		s += "=="
	case 3:
		s += "="
	}
	return base64.URLEncoding.DecodeString(s)
}

func itoa(i int) string    { return strconv.Itoa(i) }
func parseInt(s string) (int, error) { return strconv.Atoi(s) }

func max64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}

func splitN(s, sep string, n int) []string {
	return strings.SplitN(s, sep, n)
}
