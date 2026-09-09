package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestCollectorServerIsPrivateAndBounded(t *testing.T) {
	server := collectorHTTPServer(18088, http.NewServeMux())
	if server.Addr != "127.0.0.1:18088" || server.ReadHeaderTimeout <= 0 || server.WriteTimeout <= 0 {
		t.Fatalf("unsafe collector server: %+v", server)
	}
}

func TestStageMutationRequiresPost(t *testing.T) {
	called := false
	handler := collectorHTTPServer(18088, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
	})).Handler
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest("GET", "/api/stage/reset", nil))
	if called || response.Code != http.StatusMethodNotAllowed {
		t.Fatal("GET must not reset statistics")
	}
	handler.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("POST", "/api/stage/reset", nil))
	if !called {
		t.Fatal("POST should reach the stage handler")
	}
}
