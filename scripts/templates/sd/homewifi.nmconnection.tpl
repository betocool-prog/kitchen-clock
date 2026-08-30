[connection]
id=homewifi
type=wifi
interface-name=wlan0
autoconnect=true

[wifi]
mode=infrastructure
ssid=${WIFI_SSID}

[wifi-security]
key-mgmt=wpa-psk
psk=${WIFI_PSK_HEX}

[ipv4]
method=manual
address1=${STATIC_IP},${GATEWAY}
dns=${DNS_SERVERS}

[ipv6]
method=disabled
