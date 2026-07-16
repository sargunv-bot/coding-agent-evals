// egress-proxy is a minimal allowlisted HTTP CONNECT proxy for agent containers.
package main

import (
	"bufio"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"
)

type proxy struct {
	allowed map[string]struct{}
	dialer  net.Dialer
}

func main() {
	allowed := map[string]struct{}{}
	for _, host := range strings.Split(os.Getenv("CAE_ALLOWED_HOSTS"), ",") {
		host = strings.ToLower(strings.TrimSpace(host))
		if host != "" {
			allowed[host] = struct{}{}
		}
	}
	if len(allowed) == 0 {
		log.Fatal("CAE_ALLOWED_HOSTS must contain at least one exact hostname")
	}
	hosts := make([]string, 0, len(allowed))
	for host := range allowed {
		hosts = append(hosts, host)
	}
	sort.Strings(hosts)
	log.Printf("allowing TLS CONNECT to %s", strings.Join(hosts, ","))
	server := &http.Server{
		Addr:              ":3128",
		Handler:           &proxy{allowed: allowed, dialer: net.Dialer{Timeout: 15 * time.Second, KeepAlive: 30 * time.Second}},
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       90 * time.Second,
	}
	log.Fatal(server.ListenAndServe())
}

func (p *proxy) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	if request.Method == http.MethodGet && request.URL.Path == "/health" {
		writer.WriteHeader(http.StatusNoContent)
		return
	}
	if request.Method != http.MethodConnect {
		http.Error(writer, "CONNECT required", http.StatusMethodNotAllowed)
		return
	}
	host, port, err := net.SplitHostPort(request.Host)
	if err != nil || port != "443" {
		http.Error(writer, "only explicit TLS port 443 is allowed", http.StatusForbidden)
		return
	}
	host = strings.ToLower(strings.TrimSuffix(host, "."))
	if _, ok := p.allowed[host]; !ok {
		http.Error(writer, "destination denied", http.StatusForbidden)
		log.Printf("denied CONNECT host=%q", host)
		return
	}
	upstream, err := p.dialer.Dial("tcp", net.JoinHostPort(host, port))
	if err != nil {
		http.Error(writer, "upstream unavailable", http.StatusBadGateway)
		return
	}
	hijacker, ok := writer.(http.Hijacker)
	if !ok {
		upstream.Close()
		http.Error(writer, "hijacking unsupported", http.StatusInternalServerError)
		return
	}
	client, buffer, err := hijacker.Hijack()
	if err != nil {
		upstream.Close()
		return
	}
	defer client.Close()
	defer upstream.Close()
	if _, err := fmt.Fprint(client, "HTTP/1.1 200 Connection Established\r\n\r\n"); err != nil {
		return
	}
	if err := buffer.Flush(); err != nil {
		return
	}
	copyDone := make(chan struct{}, 2)
	go copyStream(upstream, buffer, copyDone)
	go copyStream(client, bufio.NewReader(upstream), copyDone)
	<-copyDone
}

func copyStream(destination io.Writer, source io.Reader, done chan<- struct{}) {
	_, _ = io.Copy(destination, source)
	done <- struct{}{}
}
