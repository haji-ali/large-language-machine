#!/usr/bin/env bash
#   deploy.sh [--dry-run] [--restart | --no-restart] [MACHINE...]
# Copies the current working tree (tracked files, plus untracked files that are
# not ignored) to every reachable machine of the Large Language Machine, then
# runs Scripts/install.sh on each to install its systemd units and restart what
# changed. Machines are handled in parallel and a summary is printed at the end.
#
# Run it from a computer on the "Large Language Machine" Wi-Fi. It asks once for
# the machines' password (they all share one) and uses it for SSH and sudo;
# press Enter at the prompt to rely on SSH keys and passwordless sudo instead.
# Set LLM_PASSWORD to skip the prompt.
#
#   --dry-run     list the files that would be copied; change nothing
#   --restart     restart every service, even where nothing changed
#   --no-restart  copy files and install units, leave running services alone
#   MACHINE       only deploy to these machines (names from the table below)
#
# Only files whose contents differ are copied. Host keys are kept in
# ~/.ssh/known_hosts.large-language-machine, so they do not clash with other
# networks' 192.168.1.x devices.

set -u

# name          ssh destination       services (comma-separated)
MACHINES="
inference       nathan@192.168.1.10   launch-ll-machine.service
uhf             nathan@192.168.1.11   read-uhf.service
rfid-dataset    nathan@192.168.1.12   read-rfid.service
button-knob     nathan@192.168.1.13   read-button.service,read-pot.service
rfid-questions  nathan@192.168.1.14   read-rfid.service
"

# Relative to the home directory on each machine
REMOTE_DIR=large-language-machine

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

all_names=$(echo "$MACHINES" | awk 'NF { print $1 }')
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

if ! { ifconfig 2>/dev/null || ip -4 addr 2>/dev/null; } | grep -q 'inet 192\.168\.1\.'; then
    echo "WARNING: this computer has no 192.168.1.x address. Is it on the Large Language Machine Wi-Fi?"
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

# result NAME STATUS DETAIL
result() {
    printf '%s\t%s\n' "$2" "$3" > "$tmp/$1.result"
}

deploy_one() {
    local name=$1 dest=$2 services=${3//,/ }
    local changed=$tmp/$name.changed n err flag

    # Compare checksums against the machine's copy; this doubles as the SSH check
    remote "$dest" "cd $REMOTE_DIR 2>/dev/null || { echo __MISSING__; exit 0; }; sha256sum -c --quiet - 2>/dev/null; exit 0" \
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

    if grep -qx __MISSING__ "$tmp/$name.check"; then
        echo "~/$REMOTE_DIR does not exist yet; copying everything"
        cp "$tmp/files" "$changed"
    else
        sed -n 's/: FAILED.*$//p' "$tmp/$name.check" > "$changed"
    fi
    n=$(wc -l < "$changed" | tr -d ' ')
    echo "$n file(s) differ from this tree"
    sed -n '1,30s/^/    /p' "$changed"
    [ "$n" -gt 30 ] && echo "    ... and $((n - 30)) more"

    flag=$restart_flag
    if [ -z "$flag" ] && grep -Ev "$NO_RESTART_PATTERN" "$changed" | grep -q .; then
        flag=--restart
    fi

    if [ $dry_run = 1 ]; then
        case $flag in
            --restart) echo "Would restart: $services" ;;
            *) echo "Would restart only services whose unit file changed or that are not running" ;;
        esac
        result "$name" OK "dry run, $n file(s) differ"
        return
    fi

    if [ "$n" -gt 0 ]; then
        # shellcheck disable=SC2086
        if ! COPYFILE_DISABLE=1 tar $TAR_OPTS -cf - -T "$changed" |
            remote "$dest" "mkdir -p $REMOTE_DIR && tar -xmf - -C $REMOTE_DIR"; then
            result "$name" FAILED "copying files failed"
            return
        fi
    fi

    echo "Running Scripts/install.sh $flag $services"
    # shellcheck disable=SC2086
    if printf '%s\n' "$LLM_PASSWORD" |
        remote "$dest" "bash $REMOTE_DIR/Scripts/install.sh --sudo-password-stdin $flag $services"; then
        result "$name" OK "$n file(s) updated"
    else
        result "$name" FAILED "install.sh reported errors (see log above)"
    fi
}

echo "Deploying $(git describe --always --dirty 2>/dev/null) to:" $names
for name in $names; do
    set -- $(echo "$MACHINES" | awk -v n="$name" '$1 == n')
    deploy_one "$1" "$2" "$3" > "$tmp/$name.log" 2>&1 &
    echo $! > "$tmp/$name.pid"
    echo "$2" > "$tmp/$name.dest"
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
