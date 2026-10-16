#!/usr/bin/env bash
#   install.sh [--restart] [--no-restart] [--dry-run] [--sudo-password-stdin] SERVICE...
# Installs this machine's systemd units from Scripts/, makes sure they are
# enabled and running, and checks they stay up. Run on the machine itself
# (Scripts/deploy.sh runs it over SSH after copying the tree).
#
#   --restart     restart the services even if their unit files are unchanged
#   --no-restart  leave running services alone, even if their unit changed
#   --dry-run     only show what would change
#   --sudo-password-stdin  read the sudo password from the first line of stdin
#                 (not needed where sudo is passwordless)
#
# read-*.service are system units in /etc/systemd/system (needs sudo).
# launch-ll-machine.service is a user unit in ~/.config/systemd/user;
# "restarting" it means restarting large-language-machine.py in its terminal.

set -u

REPO=$(cd "$(dirname "$0")/.." && pwd)
MAIN_PATTERN='python[0-9.]* .*large-language-machine\.py'
restart=auto
dry_run=0
failed=0
sudo_password=

while [ $# -gt 0 ]; do
    case $1 in
        --restart) restart=yes ;;
        --no-restart) restart=no ;;
        --dry-run) dry_run=1 ;;
        --sudo-password-stdin) IFS= read -r sudo_password ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *) break ;;
    esac
    shift
done

if [ $# -eq 0 ]; then
    echo "usage: $0 [--restart] [--no-restart] [--dry-run] [--sudo-password-stdin] SERVICE..." >&2
    exit 2
fi

as_root() {
    if [ -n "$sudo_password" ]; then
        printf '%s\n' "$sudo_password" | sudo -S -p '' "$@"
    else
        sudo -n "$@"
    fi
}

err() {
    echo "ERROR: $*"
    failed=1
}

# needs_restart UNIT_CHANGED IS_RUNNING: a stopped service is always started
needs_restart() {
    [ "$2" = 0 ] && return 0
    case $restart in
        yes) return 0 ;;
        no) return 1 ;;
    esac
    [ "$1" = 1 ]
}

# Copies unit $1 to $2 if they differ, showing the diff. Returns 0 if it changed.
update_unit() {
    local src=$1 dst=$2 sudo=$3
    if cmp -s "$src" "$dst"; then
        return 1
    fi
    if [ -e "$dst" ]; then
        echo "Updating $dst:"
        diff -u "$dst" "$src" | sed 's/^/    /'
    else
        echo "Installing new unit $dst"
    fi
    [ $dry_run = 1 ] && return 0
    # Replace rather than write through, in case $dst is a symlink
    $sudo rm -f "$dst" && $sudo install -D -m 644 "$src" "$dst"
}

# Waits for services to settle after a restart, then reports any that are not
# running or have already been restarted by systemd (i.e. crashed).
check_system_services() {
    local svc state restarts
    sleep 8
    for svc in "$@"; do
        state=$(systemctl is-active "$svc")
        restarts=$(systemctl show --property=NRestarts --value "$svc")
        if [ "$state" = active ] && [ "${restarts:-0}" = 0 ]; then
            echo "$svc: running"
        else
            err "$svc is $state after restart (crashed ${restarts:-?} times). Recent log:"
            as_root journalctl -u "$svc" -n 25 --no-pager -o cat | sed 's/^/    /'
        fi
    done
}

system_services() {
    local svc src dst changed running script restarted=()

    if [ $dry_run = 0 ] && ! as_root true 2>/dev/null; then
        err "sudo failed on $(hostname): wrong password, or a password is needed (deploy.sh asks for one)"
        return
    fi

    for svc in "$@"; do
        src=$REPO/Scripts/$svc
        dst=/etc/systemd/system/$svc
        changed=0

        if [ ! -f "$src" ]; then
            err "$src does not exist"
            continue
        fi
        script=$(sed -n 's/^ExecStart=.* \(\/[^ ]*\.py\).*/\1/p' "$src")
        if [ -n "$script" ] && [ ! -f "$script" ]; then
            err "$svc runs $script, which does not exist on $(hostname)"
        fi

        # A unit linked straight from the repo is already up to date
        if [ "$(readlink -f "$(systemctl show --property=FragmentPath --value "$svc")")" != "$(readlink -f "$src")" ]; then
            update_unit "$src" "$dst" as_root && changed=1
        fi

        if [ $dry_run = 1 ]; then
            echo "$svc: $(systemctl is-enabled "$svc" 2>/dev/null), $(systemctl is-active "$svc")"
            continue
        fi

        [ $changed = 1 ] && as_root systemctl daemon-reload
        if ! systemctl is-enabled --quiet "$svc"; then
            as_root systemctl enable "$svc" || err "could not enable $svc"
        fi

        running=0
        systemctl is-active --quiet "$svc" && running=1
        if needs_restart $changed $running; then
            echo "$svc: restarting"
            if as_root systemctl restart "$svc"; then
                restarted+=("$svc")
            else
                err "could not restart $svc"
            fi
        else
            echo "$svc: $(systemctl is-active "$svc")"
        fi
    done

    if [ ${#restarted[@]} -gt 0 ]; then
        check_system_services "${restarted[@]}"
    fi
}

main_pids() {
    pgrep -f "$MAIN_PATTERN" | tr '\n' ' '
}

# Restarts large-language-machine.py. Under the restart loop in
# launch-ll-machine.sh, killing it is enough. Otherwise its terminal is closed
# and the service opens a fresh one.
restart_main() {
    local svc=$1 pids pid parent supervised=0 new i
    pids=$(main_pids)

    for pid in $pids; do
        if { tr '\0' '\n' < "/proc/$pid/environ"; } 2>/dev/null | grep -qx 'LLM_SUPERVISED=1'; then
            supervised=1
        fi
    done

    if [ -n "$pids" ] && [ $supervised = 1 ]; then
        echo "Restarting large-language-machine.py (pid $pids)"
        kill $pids
    else
        for pid in $pids; do
            parent=$(ps -o ppid= -p "$pid" | tr -d ' ')
            if [ -n "$parent" ] && ps -o args= -p "$parent" | grep -q 'launch-ll-machine\.sh'; then
                kill "$parent"
            fi
            kill "$pid"
        done
        echo "Starting $svc"
        systemctl --user restart "$svc" || { err "could not start $svc"; return; }
    fi

    for i in $(seq 30); do
        sleep 1
        for new in $(main_pids); do
            case " $pids " in *" $new "*) ;; *)
                sleep 5
                if kill -0 "$new" 2>/dev/null; then
                    echo "large-language-machine.py: running (pid $new)"
                else
                    err "large-language-machine.py exited straight after starting"
                fi
                return ;;
            esac
        done
    done
    err "large-language-machine.py did not start within 30 seconds (is the desktop logged in?)"
}

user_service() {
    local svc=$1 src=$REPO/Scripts/$1 dst=~/.config/systemd/user/$1 changed=0 running

    export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
    if ! systemctl --user show-environment >/dev/null 2>&1; then
        err "no systemd user session for $(whoami) on $(hostname) (is the desktop logged in?)"
        return
    fi

    if [ ! -x "$REPO/Scripts/launch-ll-machine.sh" ]; then
        err "$REPO/Scripts/launch-ll-machine.sh is missing or not executable"
    fi
    if [ ! -f "$REPO/venv/bin/activate" ]; then
        err "$REPO/venv is missing; large-language-machine.py cannot start"
    fi

    update_unit "$src" "$dst" "" && changed=1

    if [ $dry_run = 1 ]; then
        echo "$svc: $(systemctl --user is-enabled "$svc" 2>/dev/null); large-language-machine.py pid: $(main_pids)"
        return
    fi

    [ $changed = 1 ] && systemctl --user daemon-reload
    if ! systemctl --user is-enabled --quiet "$svc"; then
        systemctl --user enable "$svc" || err "could not enable $svc"
    fi

    running=0
    [ -n "$(main_pids)" ] && running=1
    if needs_restart $changed $running; then
        restart_main "$svc"
    else
        echo "large-language-machine.py: running (pid $(main_pids))"
    fi
}

system=()
for svc in "$@"; do
    case $svc in
        launch-ll-machine.service) user_service "$svc" ;;
        *) system+=("$svc") ;;
    esac
done
if [ ${#system[@]} -gt 0 ]; then
    system_services "${system[@]}"
fi

exit $failed
