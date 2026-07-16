package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRejectsNonConnect(t *testing.T) {
	p := &proxy{allowed: map[string]struct{}{"example.com": {}}}
	request := httptest.NewRequest(http.MethodGet, "http://proxy.invalid/not-health", nil)
	response := httptest.NewRecorder()
	p.ServeHTTP(response, request)
	if response.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusMethodNotAllowed)
	}
}

func TestRejectsNonTLSPort(t *testing.T) {
	p := &proxy{allowed: map[string]struct{}{"example.com": {}}}
	request := httptest.NewRequest(http.MethodConnect, "http://proxy.invalid", nil)
	request.Host = "example.com:80"
	response := httptest.NewRecorder()
	p.ServeHTTP(response, request)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
	}
}

func TestRejectsUnlistedHost(t *testing.T) {
	p := &proxy{allowed: map[string]struct{}{"example.com": {}}}
	request := httptest.NewRequest(http.MethodConnect, "http://proxy.invalid", nil)
	request.Host = "unlisted.example:443"
	response := httptest.NewRecorder()
	p.ServeHTTP(response, request)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
	}
}
