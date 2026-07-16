#!/usr/bin/env bash
set -euo pipefail

label="io.sargunv.coding-agent-evals=true"
network="cae-isolation-$RANDOM-$$"
proxy="cae-isolation-proxy-$$"
node_image="docker.io/library/node@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3"
proxy_image="localhost/coding-agent-evals/egress-proxy:dev"

cleanup() {
  podman rm -f "$proxy" >/dev/null 2>&1 || true
  podman network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT

podman network create --internal --disable-dns --label "$label" "$network" >/dev/null
podman run -d --name "$proxy" --network podman --label "$label" \
  -e CAE_ALLOWED_HOSTS=example.com "$proxy_image" >/dev/null
podman network connect "$network" "$proxy"
proxy_ip="$(podman inspect "$proxy" --format "{{with index .NetworkSettings.Networks \"$network\"}}{{.IPAddress}}{{end}}")"
proxy_url="http://$proxy_ip:3128"

allowed="$(podman run --rm --network "$network" \
  -e HTTPS_PROXY="$proxy_url" -e NODE_USE_ENV_PROXY=1 "$node_image" \
  node -e 'fetch("https://example.com").then(r=>console.log(r.status)).catch(()=>process.exit(1))')"

set +e
podman run --rm --network "$network" \
  -e HTTPS_PROXY="$proxy_url" -e NODE_USE_ENV_PROXY=1 "$node_image" \
  node -e 'fetch("https://github.com").then(()=>process.exit(0)).catch(()=>process.exit(1))' \
  >/dev/null 2>&1
denied_exit=$?
podman run --rm --network "$network" "$node_image" \
  node -e 'fetch("https://example.com").then(()=>process.exit(0)).catch(()=>process.exit(1))' \
  >/dev/null 2>&1
direct_exit=$?
set -e

[[ "$allowed" == "200" ]]
[[ $denied_exit -ne 0 ]]
[[ $direct_exit -ne 0 ]]
printf 'allowed=%s denied_exit=%s direct_exit=%s\n' "$allowed" "$denied_exit" "$direct_exit"
