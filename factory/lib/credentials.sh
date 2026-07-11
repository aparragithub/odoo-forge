#!/usr/bin/env bash

read_secret_value() {
    local name="$1"
    local file_name="${name}_FILE"
    local file_path="${!file_name:-}"

    if [[ -n "$file_path" ]]; then
        if [[ ! -r "$file_path" ]]; then
            echo "ERROR: secret file for ${name} is not readable" >&2
            exit 1
        fi
        cat "$file_path"
        return
    fi
    printf '%s' "${!name:-}"
}
