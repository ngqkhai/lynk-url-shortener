#!/usr/bin/env bash
set -euo pipefail
# Pass a directory under /tmp; the CA private key never enters app/Traefik containers.
key_dir="${1:?Usage: generate-local-keys.sh /tmp/lynk-keys}"
namespace="${LYNK_NAMESPACE:-lynk-local}"
mkdir -p "$key_dir"
chmod 700 "$key_dir"
if [[ -f "$key_dir/jwt-private.pem" ]]; then
  for file in jwt-public.pem ca.crt server.crt server.key client.crt client.key; do
    [[ -f "$key_dir/$file" ]] || { echo "Incomplete key directory: restore $file." >&2; exit 1; }
  done
  exit 0
fi
umask 077
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$key_dir/jwt-private.pem" 2>/dev/null
openssl pkey -in "$key_dir/jwt-private.pem" -pubout -out "$key_dir/jwt-public.pem"
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 365 -subj '/CN=Lynk local CA' -keyout "$key_dir/ca.key" -out "$key_dir/ca.crt" 2>/dev/null
for identity in server client; do
  if [[ "$identity" == server ]]; then
    cn=auth-service-gateway
    printf '%s\n' "subjectAltName=DNS:auth-service-gateway,DNS:auth-service-gateway.$namespace.svc,DNS:localhost" 'extendedKeyUsage=serverAuth' > "$key_dir/$identity.ext"
  else
    cn=lynk-traefik
    printf '%s\n' 'extendedKeyUsage=clientAuth' > "$key_dir/$identity.ext"
  fi
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$cn" -keyout "$key_dir/$identity.key" -out "$key_dir/$identity.csr" 2>/dev/null
  openssl x509 -req -in "$key_dir/$identity.csr" -CA "$key_dir/ca.crt" -CAkey "$key_dir/ca.key" -CAcreateserial -days 365 -sha256 -extfile "$key_dir/$identity.ext" -out "$key_dir/$identity.crt" 2>/dev/null
done
