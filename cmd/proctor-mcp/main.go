// proctor-mcp exposes a single ask_user MCP tool over stdio.
// It is intentionally dependency-free so it can be compiled as a static binary.
package main

import (
	"bufio"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type response struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Result  any             `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type toolCall struct {
	Name      string `json:"name"`
	Arguments struct {
		Question string `json:"question"`
	} `json:"arguments"`
}

type question struct {
	QuestionID string  `json:"question_id"`
	RunID      string  `json:"run_id"`
	TaskID     string  `json:"task_id"`
	Text       string  `json:"text"`
	CreatedAt  float64 `json:"created_at"`
}

type answer struct {
	QuestionID string  `json:"question_id"`
	Text       string  `json:"text"`
	Proctor    string  `json:"proctor"`
	CreatedAt  float64 `json:"created_at"`
}

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 64*1024), 1024*1024)
	encoder := json.NewEncoder(os.Stdout)
	for scanner.Scan() {
		var req request
		if err := json.Unmarshal(scanner.Bytes(), &req); err != nil {
			_ = encoder.Encode(response{JSONRPC: "2.0", Error: &rpcError{-32700, err.Error()}})
			continue
		}
		if req.ID == nil {
			continue // notification
		}
		resp := dispatch(req)
		if err := encoder.Encode(resp); err != nil {
			fmt.Fprintln(os.Stderr, "proctor-mcp: encode:", err)
			return
		}
	}
	if err := scanner.Err(); err != nil {
		fmt.Fprintln(os.Stderr, "proctor-mcp: stdin:", err)
	}
}

func dispatch(req request) response {
	resp := response{JSONRPC: "2.0", ID: req.ID}
	switch req.Method {
	case "initialize":
		resp.Result = map[string]any{
			"protocolVersion": "2024-11-05",
			"capabilities":    map[string]any{"tools": map[string]any{}},
			"serverInfo":      map[string]any{"name": "coding-agent-evals-proctor", "version": "0.1.0"},
		}
	case "ping":
		resp.Result = map[string]any{}
	case "tools/list":
		resp.Result = map[string]any{"tools": []any{map[string]any{
			"name":        "ask_user",
			"description": "Ask the user a consequential clarification question. Do not use this for information available in the repository or to request a solution.",
			"inputSchema": map[string]any{
				"type":       "object",
				"properties": map[string]any{"question": map[string]any{"type": "string", "minLength": 1}},
				"required":   []string{"question"},
			},
		}}}
	case "tools/call":
		var call toolCall
		if err := json.Unmarshal(req.Params, &call); err != nil || call.Name != "ask_user" || strings.TrimSpace(call.Arguments.Question) == "" {
			resp.Error = &rpcError{-32602, "tools/call requires ask_user with a non-empty question"}
			return resp
		}
		value, err := ask(strings.TrimSpace(call.Arguments.Question))
		if err != nil {
			resp.Result = map[string]any{
				"content": []any{map[string]any{"type": "text", "text": "The proctor could not answer: " + err.Error()}},
				"isError": true,
			}
		} else {
			resp.Result = map[string]any{
				"content": []any{map[string]any{"type": "text", "text": value.Text}},
			}
		}
	default:
		resp.Error = &rpcError{-32601, "method not found"}
	}
	return resp
}

func ask(text string) (answer, error) {
	root := env("CAE_PROCTOR_QUEUE", "/proctor")
	runID := env("CAE_RUN_ID", "unknown-run")
	taskID := env("CAE_TASK_ID", "unknown-task")
	timeout := 30 * time.Minute
	if raw := os.Getenv("CAE_PROCTOR_TIMEOUT"); raw != "" {
		parsed, err := time.ParseDuration(raw)
		if err != nil {
			return answer{}, fmt.Errorf("invalid CAE_PROCTOR_TIMEOUT: %w", err)
		}
		timeout = parsed
	}
	for _, directory := range []string{root, filepath.Join(root, "questions"), filepath.Join(root, "answers")} {
		if err := os.MkdirAll(directory, 0o777); err != nil {
			return answer{}, err
		}
	}
	id, err := newID()
	if err != nil {
		return answer{}, err
	}
	q := question{id, runID, taskID, text, float64(time.Now().UnixNano()) / 1e9}
	final := filepath.Join(root, "questions", id+".json")
	temporary := final + ".tmp"
	payload, _ := json.MarshalIndent(q, "", "  ")
	payload = append(payload, '\n')
	if err := os.WriteFile(temporary, payload, 0o644); err != nil {
		return answer{}, err
	}
	if err := os.Rename(temporary, final); err != nil {
		return answer{}, err
	}
	fmt.Fprintf(os.Stderr, "[PROCTOR_QUESTION] %s %s\n", id, text)

	answerPath := filepath.Join(root, "answers", id+".json")
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		payload, err := os.ReadFile(answerPath)
		if err == nil {
			var value answer
			if err := json.Unmarshal(payload, &value); err != nil {
				return answer{}, fmt.Errorf("invalid proctor answer: %w", err)
			}
			if value.QuestionID != id || strings.TrimSpace(value.Text) == "" || strings.TrimSpace(value.Proctor) == "" {
				return answer{}, fmt.Errorf("answer failed provenance validation")
			}
			fmt.Fprintf(os.Stderr, "[PROCTOR_ANSWERED] %s by %s\n", id, value.Proctor)
			return value, nil
		}
		if !os.IsNotExist(err) {
			return answer{}, err
		}
		time.Sleep(200 * time.Millisecond)
	}
	return answer{}, fmt.Errorf("timeout waiting for answer to %s", id)
}

func newID() (string, error) {
	buffer := make([]byte, 8)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return fmt.Sprintf("q-%d-%s", time.Now().UnixNano(), hex.EncodeToString(buffer)), nil
}

func env(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
