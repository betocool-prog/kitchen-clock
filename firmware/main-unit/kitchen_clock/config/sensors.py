# Sensor unit inventory.
#
# The kitchen-clock main unit polls two bonded BLE peripherals (one
# stood indoors, one stood outdoors, both running our UF2 firmware
# `firmware/outdoor-sensor`). The MACs of those peripherals are baked
# here so:
#
#   - the GATT client at runtime knows whom to subscribe to,
#   - debouncing / pairing / role labelling does not require
#     scanning at startup,
#   - docs / release artefacts reproduce which sensor feeds which
#     dashboard tile.
#
# Update procedure: power on the next sensor unit, run
#
#   bluetoothctl scan on          # 4-5 s
#   bluetoothctl scan off
#   python scripts/probe-ble-devices.py --filter kclock
#
# and replace the placeholder entry below with the discovered
# `(mac, name, location)` triplet. Keep `'outside'` / `'inside'`
# as the location strings — they flow into UI labelling (layout v5
# renders the title as "Outside" / "Inside") and the runner's
# journal state lines.

KCLOCK_SENSORS = (
    # Discovered on 2026-08-30 from `kclock-d0`. RSSI blank on
    # bleak 3.x unless we read details['rssi'].
    ("D0:44:B3:EE:AC:9F", "kclock-d0", "outside"),

    # Discovered on 2026-08-30. Labelled "inside" by convention;
    # swap with the outside entry above if the physical placement
    # reverses later. RSSI blank on bleak 3.x unless we read
    # `details['rssi']`.
    ("D3:B3:63:7C:F2:30", "kclock-d3", "inside"),
)


def by_mac(mac: str):
    """Lookup a single sensor tuple by MAC address."""
    want = mac.upper()
    for s in KCLOCK_SENSORS:
        if s[0].upper() == want:
            return s
    return None


def by_location(location: str):
    """Lookup a single sensor tuple by location string."""
    for s in KCLOCK_SENSORS:
        if s[2] == location:
            return s
    return None
