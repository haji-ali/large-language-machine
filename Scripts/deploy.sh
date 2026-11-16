#!/usr/bin/env bash
#   deploy.sh [--dry-run] [--restart | --no-restart] [MACHINE...]
# Copies the current working tree (tracked files, plus untracked files that are
# not ignored) to every reachable machine of the Large Language Machine, then
# runs Scripts/install.sh on each to install its systemd units and restart what
# changed. Machines are handled in parallel and a summary is printed at the end.
# The machines, their addresses and services, the login and the directory to
# copy to all come from llm.conf.
#
# Run it from a computer on the "Large Language Machine" Wi-Fi. It asks once for
# the machines' password (they all share one) and uses it for SSH and sudo;
# press Enter at the prompt to rely on SSH keys and passwordless sudo instead.
# Set LLM_PASSWORD to skip the prompt.
#
#   --dry-run     list the files and units that would be installed (new) or
#                 replaced, with their full paths on each machine; change nothing
#   --restart     restart every service, even where nothing changed
#   --no-restart  copy files and install units, leave running services alone
#   MACHINE       only deploy to these machines (names from MACHINES in llm.conf)
#
# Only files whose contents differ are copied. Host keys are kept in
# ~/.ssh/known_hosts.large-language-machine, so they do not clash with devices
# at the same addresses on other networks.

set -u

# Changes only under these paths do not need services restarting
NO_RESTART_PATTERN='^(Docs/|Images/|Tests/|Tools/|README\.md$|LICENSE$|index\.html$|nixpacks\.toml$|\.gitignore$|.*\.pdf$)'

usage() {
    sed -n '2,/^$/s/^# \{0,1\}//p' "$0" >&2
    exit 2
}

dry_run=0
restart_flag=
selected=
while [ $# -gt 0 ]; do
    case $1 in
        --dry-run) dry_run=1 ;;
        --restart) restart_flag=--restart ;;
        --no-restart) restart_flag=--no-restart ;;
        -h|--help) usage ;;
        -*) echo "unknown option: $1" >&2; usage ;;
        *) selected="$selected $1" ;;
    esac
    shift
done

cd "$(dirname "$0")/.." || exit 1

if command -v python3 >/dev/null; then
    python3 llm_config.py --quiet || { echo "Fix llm.conf before deploying." >&2; exit 1; }
fi
# shellcheck source=../llm.conf
source llm.conf || exit 1

# name ip services, one machine per line
machine_rows() {
    echo "$MACHINES" | awk '{ sub(/#.*/, "") } NF'
}

all_names=$(machine_rows | awk '{ print $1 }')
for name in $selected; do
    if ! echo "$all_names" | grep -qx "$name"; then
        echo "unknown machine '$name'; choose from:" $all_names >&2
        exit 2
    fi
done
names=${selected:-$all_names}

tmp=$(mktemp -d "${TMPDIR:-/tmp}/llm-deploy.XXXXXX") || exit 1
trap 'rm -rf "$tmp"' EXIT

# Files to deploy, and their checksums for comparing with each machine's copy
git -c core.quotePath=false ls-files --cached --others --exclude-standard |
    while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done > "$tmp/files"
if command -v sha256sum >/dev/null; then
    sha256=sha256sum
else
    sha256="shasum -a 256"
fi
tr '\n' '\0' < "$tmp/files" | xargs -0 $sha256 > "$tmp/manifest" || exit 1

# Catch syntax errors here rather than as a crash-looping service
if command -v python3 >/dev/null; then
    grep -E '^[^/]+\.py$' "$tmp/files" | tr '\n' '\0' | xargs -0 python3 -c '
import ast, sys
bad = 0
for f in sys.argv[1:]:
    try:
        ast.parse(open(f, encoding="utf-8").read(), f)
    except SyntaxError as e:
        print(f"{f}:{e.lineno}: {e.msg}")
        bad = 1
sys.exit(bad)' || { echo "Fix the syntax errors above before deploying." >&2; exit 1; }
fi

subnet=${ROUTER_IP%.*}.
if ! { ifconfig 2>/dev/null || ip -4 addr 2>/dev/null; } | grep -qF "inet $subnet"; then
    echo "WARNING: this computer has no ${subnet}x address. Is it on the $WIFI_SSID Wi-Fi?"
fi

if tar --version 2>/dev/null | grep -q bsdtar; then
    TAR_OPTS="--no-xattrs --no-mac-metadata"
else
    TAR_OPTS=
fi

if [ -z "${LLM_PASSWORD+set}" ]; then
    if [ -t 0 ]; then
        IFS= read -rs -p "Password for the machines (Enter for SSH keys only): " LLM_PASSWORD
        echo
    else
        LLM_PASSWORD=
    fi
fi
export LLM_PASSWORD

# ssh reads the password from this helper rather than prompting on the terminal
cat > "$tmp/askpass" <<'EOF'
#!/bin/sh
printf '%s\n' "$LLM_PASSWORD"
EOF
chmod 700 "$tmp/askpass"
if [ -n "$LLM_PASSWORD" ]; then
    export SSH_ASKPASS="$tmp/askpass" SSH_ASKPASS_REQUIRE=force
    AUTH_OPTS="-o NumberOfPasswordPrompts=1"
else
    AUTH_OPTS="-o BatchMode=yes"
fi

mkdir -p ~/.ssh
SSH_OPTS="$AUTH_OPTS -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=3
    -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$HOME/.ssh/known_hosts.large-language-machine"

remote() {
    # shellcheck disable=SC2086
    ssh $SSH_OPTS "$@"
}

# list_files LABEL LIST ROOT: shows the first 30 paths in LIST under ROOT
list_files() {
    local count
    count=$(wc -l < "$2" | tr -d ' ')
    awk -v p="$(printf '    %-8s %s/' "$1" "$3")" 'NR <= 30 { print p $0 }' "$2"
    if [ "$count" -gt 30 ]; then
        echo "    ... and $((count - 30)) more $1 files under $3/"
    fi
}

# result NAME STATUS DETAIL
result() {
    printf '%s\t%s\n' "$2" "$3" > "$tmp/$1.result"
}

deploy_one() {
    local name=$1 dest=$2 services=${3//,/ }
    local changed=$tmp/$name.changed new=$tmp/$name.new replace=$tmp/$name.replace
    local n root qroot units err flag

    # Compare checksums against the machine's copy; this doubles as the SSH check.
    # LLM_DIR is relative to the home directory unless it is absolute.
    remote "$dest" "r=$(printf %q "$LLM_DIR"); case \$r in /*) ;; *) r=\$HOME/\$r ;; esac
        echo \"__ROOT__ \$r\"; cd \"\$r\" 2>/dev/null || { echo __MISSING__; exit 0; }
        sha256sum -c --quiet - 2>/dev/null; exit 0" \
        < "$tmp/manifest" > "$tmp/$name.check" 2> "$tmp/$name.err"
    if [ $? -eq 255 ]; then
        err=$(grep -v '^Warning: Permanently added' "$tmp/$name.err" | tail -n 1)
        echo "$err"
        case $err in
            *"Permission denied"*)
                result "$name" FAILED "SSH login refused; check the password" ;;
            *"Host key verification failed"*|*"IDENTIFICATION HAS CHANGED"*)
                result "$name" FAILED "host key changed; check ~/.ssh/known_hosts.large-language-machine" ;;
            *)
                result "$name" UNREACHABLE "${err:-ssh failed}" ;;
        esac
        return
    fi

    root=$(sed -n 's/^__ROOT__ //p' "$tmp/$name.check")
    qroot=$(printf %q "$root")
    if grep -qx __MISSING__ "$tmp/$name.check"; then
        echo "$root does not exist yet; every file is new"
        cp "$tmp/files" "$new"
        : > "$replace"
    else
        sed -n 's/: FAILED open or read$//p' "$tmp/$name.check" > "$new"
        sed -n 's/: FAILED$//p' "$tmp/$name.check" > "$replace"
    fi
    cat "$replace" "$new" > "$changed"
    n=$(wc -l < "$changed" | tr -d ' ')
    echo "Files: $(wc -l < "$replace" | tr -d ' ') to replace, $(wc -l < "$new" | tr -d ' ') new, the rest unchanged"
    list_files replace "$replace" "$root"
    list_files new "$new" "$root"

    flag=$restart_flag
    if [ -z "$flag" ] && grep -Ev "$NO_RESTART_PATTERN" "$changed" | grep -q .; then
        flag=--restart
    fi

    if [ $dry_run = 1 ]; then
        # Check the units against the machine without installing anything: the new
        # unit files go to a temporary directory there, which is removed afterwards
        echo "Units:"
        units=
        for svc in $services; do
            units="$units Scripts/$svc"
        done
        # shellcheck disable=SC2086
        COPYFILE_DISABLE=1 tar $TAR_OPTS -cf - Scripts/install.sh llm.conf $units -C "$tmp" files |
            remote "$dest" "d=\$(mktemp -d) && tar -xmf - -C \"\$d\" &&
                LLM_REPO=$qroot LLM_UNITS_DIR=\$d/Scripts LLM_CONFIG=\$d/llm.conf LLM_TREE_FILES=\$d/files \\
                bash \"\$d/Scripts/install.sh\" --dry-run $services; s=\$?; rm -rf \"\$d\"; exit \$s" |
            sed 's/^/  /'
        if [ "${PIPESTATUS[1]}" != 0 ]; then
            result "$name" FAILED "dry run found problems (see log above)"
            return
        fi
        case $flag in
            --restart) echo "Would restart: $services" ;;
            *) echo "Would restart only services whose unit file changed or that are not running" ;;
        esac
        result "$name" OK "dry run: $(wc -l < "$replace" | tr -d ' ') to replace, $(wc -l < "$new" | tr -d ' ') new"
        return
    fi

    if [ "$n" -gt 0 ]; then
        # shellcheck disable=SC2086
        if ! COPYFILE_DISABLE=1 tar $TAR_OPTS -cf - -T "$changed" |
            remote "$dest" "mkdir -p $qroot && tar -xmf - -C $qroot"; then
            result "$name" FAILED "copying files failed"
            return
        fi
    fi

    echo "Running Scripts/install.sh $flag $services"
    # shellcheck disable=SC2086
    if printf '%s\n' "$LLM_PASSWORD" |
        remote "$dest" "bash $qroot/Scripts/install.sh --sudo-password-stdin $flag $services"; then
        result "$name" OK "$(wc -l < "$replace" | tr -d ' ') replaced, $(wc -l < "$new" | tr -d ' ') new"
    else
        result "$name" FAILED "install.sh reported errors (see log above)"
    fi
}

echo "Deploying $(git describe --always --dirty 2>/dev/null) to:" $names
for name in $names; do
    set -- $(machine_rows | awk -v n="$name" '$1 == n')
    deploy_one "$1" "$SSH_USER@$2" "$3" > "$tmp/$name.log" 2>&1 &
    echo $! > "$tmp/$name.pid"
    echo "$SSH_USER@$2" > "$tmp/$name.dest"
done

# Print each machine's log as it finishes
pending=$names
while [ -n "$pending" ]; do
    still=
    for name in $pending; do
        pid=$(cat "$tmp/$name.pid")
        if kill -0 "$pid" 2>/dev/null; then
            still="$still $name"
            continue
        fi
        wait "$pid"
        [ -f "$tmp/$name.result" ] || result "$name" FAILED "deploy.sh error (see log above)"
        echo
        echo "=== $name ($(cat "$tmp/$name.dest")): $(cut -f1 "$tmp/$name.result")"
        sed 's/^/  /' "$tmp/$name.log"
    done
    pending=$still
    [ -n "$pending" ] && sleep 1
done

echo
echo "=== Summary"
status=0
for name in $names; do
    IFS="$(printf '\t')" read -r state detail < "$tmp/$name.result"
    printf '  %-15s %-12s %s\n' "$name" "$state" "$detail"
    [ "$state" = OK ] || status=1
done
exit $status
