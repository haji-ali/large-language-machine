#!/usr/bin/env bash
#   wifi-watchdog.sh
# Keeps this machine on the WIFI_SSID network from llm.conf. Run as root by
# wifi-watchdog.service; needs NetworkManager.
#
# At start it makes the NetworkManager profile for WIFI_SSID robust: available
# without anyone logged in, password kept in the profile rather than a desktop
# keyring, never giving up on reconnecting, and Wi-Fi power saving off. It
# keeps a copy of the profile and restores it if the profile goes missing.
#
# Then, every CHECK_INTERVAL seconds, it checks the Wi-Fi is connected and the
# router answers. After RECONNECT_AFTER seconds of not, it reconnects by hand:
# when a connection attempt fails at the password stage (e.g. while the router
# is still starting up), NetworkManager assumes the password is wrong and stops
# connecting automatically until someone reconnects.
#
# It leaves a connection to any other network alone, so a machine can be put on
# another network by hand (e.g. to download updates). To keep Wi-Fi
# disconnected, stop it first: sudo systemctl stop wifi-watchdog

set -u

REPO=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../llm.conf
source "$REPO/llm.conf" || exit 1

CHECK_INTERVAL=15
RECONNECT_AFTER=60
BACKUP=/var/lib/large-language-machine/wifi.nmconnection
RESTORED=/etc/NetworkManager/system-connections/llm-wifi-restored.nmconnection

uuid=
down_since=
router_seen=0
last_note=

log() {
    echo "$*"
}

# Logs a message only if it differs from the previous note, so repeated checks stay quiet
note() {
    [ "$*" = "$last_note" ] || log "$*"
    last_note=$*
}

nm_get() {
    nmcli --escape no -g "$1" connection show uuid "$2" 2>/dev/null
}

# Prints the UUID of the Wi-Fi profile for $WIFI_SSID
profile_uuid() {
    local u type
    nmcli -t -f UUID,TYPE connection show 2>/dev/null | while IFS=: read -r u type; do
        if [ "$type" = 802-11-wireless ] && [ "$(nm_get 802-11-wireless.ssid "$u")" = "$WIFI_SSID" ]; then
            echo "$u"
            break
        fi
    done
}

wifi_device() {
    nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2 == "wifi" { print $1; exit }'
}

device_state() {
    nmcli -t -f DEVICE,STATE device 2>/dev/null | awk -F: -v d="$1" '$1 == d { print $2; exit }'
}

router_answers() {
    ping -c 1 -W 2 "$ROUTER_IP" >/dev/null 2>&1
}

# Sets the profile's options for unattended use, where they differ
harden() {
    local changes=() names=() psk
    [ "$(nm_get connection.autoconnect "$uuid")" = yes ] ||
        changes+=(connection.autoconnect yes)
    # 0 means keep retrying for ever
    [ "$(nm_get connection.autoconnect-retries "$uuid" | cut -d' ' -f1)" = 0 ] ||
        changes+=(connection.autoconnect-retries 0)
    # Empty means available to every user, and with nobody logged in
    [ -z "$(nm_get connection.permissions "$uuid")" ] ||
        changes+=(connection.permissions "")
    # 2 means disabled
    [ "$(nm_get 802-11-wireless.powersave "$uuid" | cut -d' ' -f1)" = 2 ] ||
        changes+=(802-11-wireless.powersave 2)
    names=("${changes[@]}")
    # 0 means the password is stored in the profile itself
    if [ -n "$(nm_get 802-11-wireless-security.key-mgmt "$uuid")" ] &&
        [ "$(nm_get 802-11-wireless-security.psk-flags "$uuid" | cut -d' ' -f1)" != 0 ]; then
        psk=$(nmcli --escape no -s -g 802-11-wireless-security.psk connection show uuid "$uuid" 2>/dev/null)
        if [ -n "$psk" ]; then
            changes+=(802-11-wireless-security.psk-flags 0 802-11-wireless-security.psk "$psk")
            names+=(802-11-wireless-security.psk-flags 0 "(password moved into the profile)")
        else
            log "WARNING: the password for $WIFI_SSID is kept in a desktop keyring, so it is only" \
                "available while someone is logged in. To store it in the profile, run:" \
                "sudo nmcli connection modify $uuid wifi-sec.psk-flags 0 wifi-sec.psk 'PASSWORD'"
        fi
    fi
    if [ ${#changes[@]} -gt 0 ]; then
        if nmcli connection modify uuid "$uuid" "${changes[@]}"; then
            log "Updated the $WIFI_SSID profile:" "${names[@]}"
        else
            log "WARNING: could not update the $WIFI_SSID profile"
        fi
    fi
}

# Keeps a copy of the profile's keyfile, which holds the password
backup_profile() {
    local file
    file=$(nmcli --escape no -t -f UUID,FILENAME connection show 2>/dev/null |
        awk -v u="$uuid" 'index($0, u ":") == 1 { print substr($0, length(u) + 2); exit }')
    case $file in
        /etc/NetworkManager/system-connections/*) ;;
        *) note "The $WIFI_SSID profile is not a keyfile (${file:-no file}), so no copy is kept"; return ;;
    esac
    if [ -f "$file" ] && ! cmp -s "$file" "$BACKUP"; then
        mkdir -p "$(dirname "$BACKUP")" && install -m 600 "$file" "$BACKUP" &&
            log "Saved a copy of the $WIFI_SSID profile to $BACKUP"
    fi
}

restore_profile() {
    if [ ! -f "$BACKUP" ]; then
        note "ERROR: there is no Wi-Fi profile for $WIFI_SSID and no copy of one to restore." \
            "Connect to it once by hand and this service will keep a copy from then on."
        return 1
    fi
    log "The $WIFI_SSID profile is missing; restoring it from $BACKUP"
    install -m 600 "$BACKUP" "$RESTORED" && nmcli connection load "$RESTORED"
    uuid=$(profile_uuid)
    [ -n "$uuid" ]
}

reconnect() {
    local dev=$1 out
    if [ "$(nmcli radio wifi 2>/dev/null)" != enabled ]; then
        log "Wi-Fi radio is off; turning it on"
        rfkill unblock wifi 2>/dev/null
        nmcli radio wifi on
    fi
    uuid=$(profile_uuid)
    if [ -z "$uuid" ]; then
        restore_profile || return
        harden
    fi
    log "Reconnecting $dev to $WIFI_SSID"
    nmcli device wifi rescan ifname "$dev" >/dev/null 2>&1 && sleep 3
    if out=$(nmcli --wait 45 connection up uuid "$uuid" ifname "$dev" 2>&1); then
        log "Reconnected to $WIFI_SSID"
        backup_profile
    else
        log "Reconnecting failed: $out"
    fi
}

unhealthy() {
    local dev=$1 reason=$2 now
    now=$(date +%s)
    if [ -z "$down_since" ]; then
        down_since=$now
        log "$reason"
    fi
    if [ $((now - down_since)) -ge $RECONNECT_AFTER ]; then
        # Wait another RECONNECT_AFTER before the next attempt
        down_since=$now
        reconnect "$dev"
    fi
}

check() {
    local dev state active
    if ! nmcli -t general status >/dev/null 2>&1; then
        note "NetworkManager is not running"
        return
    fi
    dev=$(wifi_device)
    if [ -z "$dev" ]; then
        note "No Wi-Fi device found"
        return
    fi
    state=$(device_state "$dev")
    case $state in
        connected*)
            active=$(nmcli --escape no -g GENERAL.CON-UUID device show "$dev" 2>/dev/null)
            # The profile may have been recreated (with a new UUID) since it was looked up
            [ "$active" = "$uuid" ] || uuid=$(profile_uuid)
            if [ "$active" != "$uuid" ]; then
                note "$dev is connected to another network; leaving it alone"
            elif router_answers; then
                router_seen=1
                note "Connected to $WIFI_SSID"
            elif [ $router_seen = 0 ]; then
                # Some routers never answer pings; only rely on them once one has
                note "Connected to $WIFI_SSID (the router at $ROUTER_IP has not answered a ping yet)"
            else
                unhealthy "$dev" "Connected to $WIFI_SSID, but the router at $ROUTER_IP stopped answering"
                return
            fi
            down_since= ;;
        unmanaged*)
            note "$dev is not managed by NetworkManager" ;;
        *)
            if router_answers; then
                # Reached through another interface, e.g. Ethernet
                note "$dev is $state, but the router answers through another interface"
                down_since=
            else
                unhealthy "$dev" "Wi-Fi is $state"
            fi ;;
    esac
}

until nmcli -t general status >/dev/null 2>&1; do
    note "Waiting for NetworkManager"
    sleep 5
done

uuid=$(profile_uuid)
if [ -n "$uuid" ] || restore_profile; then
    harden
    backup_profile
fi

if command -v iw >/dev/null && iw reg get 2>/dev/null | grep -q '^country 00'; then
    log "WARNING: the Wi-Fi country is not set, so channels 12-13 and many 5 GHz channels" \
        "cannot be used. Set it with: sudo raspi-config nonint do_wifi_country GB"
fi

while true; do
    check
    sleep $CHECK_INTERVAL
done
