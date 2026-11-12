#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 {flask_secret_key|web_auth_password|prometheus_password|openai_api_key|huggingface_api_key|cohere_api_key}" >&2
    exit 2
fi

case "$1" in
    flask_secret_key)
        secret_file=flask_secret_key.txt
        services=(app)
        minimum_length=32
        ;;
    web_auth_password)
        secret_file=web_auth_password.txt
        services=(app)
        minimum_length=16
        ;;
    prometheus_password)
        secret_file=prometheus_password.txt
        services=(app prometheus)
        minimum_length=16
        ;;
    openai_api_key)
        secret_file=openai_api_key.txt
        services=(app scheduler)
        minimum_length=1
        ;;
    huggingface_api_key)
        secret_file=huggingface_api_key.txt
        services=(app scheduler)
        minimum_length=1
        ;;
    cohere_api_key)
        secret_file=cohere_api_key.txt
        services=(app scheduler)
        minimum_length=1
        ;;
    *)
        echo "Unsupported secret name: $1" >&2
        exit 2
        ;;
esac

deploy_path="${DEPLOY_PATH:-/opt/social-media-agent}"
current_release="${deploy_path}/current"
config_dir="${CONFIG_DIR:-/etc/social-media-agent}"
secret_path="${config_dir}/secrets/${secret_file}"

if [[ ! -f "${current_release}/docker-compose.yml" || ! -f "${current_release}/docker-compose.tls.yml" ]]; then
    echo "The current production Compose release was not found." >&2
    exit 1
fi
if [[ ! -f "${current_release}/.env" || ! -f "$secret_path" || -L "$secret_path" ]]; then
    echo "The production environment or regular secret file is missing." >&2
    exit 1
fi
if [[ ! -w "${config_dir}/secrets" ]]; then
    echo "The secrets directory must be writable by the deployment operator." >&2
    exit 1
fi

read -r -s -p "New value for ${secret_file}: " new_secret </dev/tty
printf '\n' >/dev/tty
read -r -s -p "Confirm new value: " confirmation </dev/tty
printf '\n' >/dev/tty

if [[ -z "$new_secret" || "$new_secret" != "$confirmation" ]]; then
    echo "Secret values must be non-empty and match." >&2
    exit 1
fi
if (( ${#new_secret} < minimum_length )); then
    echo "The new value must be at least ${minimum_length} characters long." >&2
    exit 1
fi

umask 077
temporary_file=$(mktemp "${config_dir}/secrets/.${secret_file}.XXXXXX")
trap 'rm -f -- "${temporary_file:-}"' EXIT
printf '%s\n' "$new_secret" > "$temporary_file"
chmod 0640 "$temporary_file"
mv -f -- "$temporary_file" "$secret_path"
temporary_file=

compose=(
    docker compose
    --project-name social-media-agent
    --project-directory "$current_release"
    --env-file "${current_release}/.env"
    -f "${current_release}/docker-compose.yml"
    -f "${current_release}/docker-compose.tls.yml"
)
"${compose[@]}" up -d --force-recreate "${services[@]}"

ready=0
for attempt in $(seq 1 30); do
    if "${compose[@]}" exec -T app python -c \
        "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/ready', timeout=5)"; then
        ready=1
        break
    fi
    sleep 2
done
if [[ "$ready" -ne 1 ]]; then
    echo "Secret was replaced, but the application did not become ready; investigate the deployment." >&2
    exit 1
fi

echo "Secret replaced and consuming services recreated. Verify the integration before revoking any previous provider credential."
