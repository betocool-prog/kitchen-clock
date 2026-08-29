#include "ble.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/services/ess.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>
#include <string.h>

/* Local-name format: "kclock-AB" where AB is the last byte of the
 * public BLE address rendered as two hex digits.
 */
#define KCLOCK_LOCAL_NAME_MAX  sizeof("kclock-XXXX") /* incl. NUL */

/* Custom 128-bit UUIDs for the battery-voltage service. The first
 * four bytes spell "kclk" (0x6b 0x63 0x6c 0x6b) so the bytes are
 * recognisable in a hex dump. The trailing octet identifies the
 * characteristic within the service.
 *
 *   Service:        6b 63 6c 6b - 00 01 - 00 00 - 00 00 - 00 00 00 00 00 01
 *   Battery mV:     6b 63 6c 6b - 00 01 - 00 00 - 00 00 - 00 00 00 00 00 02
 */
static const uint8_t kclock_batt_svc_uuid[16] = {
    0x6b, 0x63, 0x6c, 0x6b, 0x00, 0x01, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01
};
static const uint8_t kclock_batt_mv_uuid[16] = {
    0x6b, 0x63, 0x6c, 0x6b, 0x00, 0x01, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02
};

static char         local_name[KCLOCK_LOCAL_NAME_MAX];
static uint16_t     last_batt_mV;

/* Static GATT: a primary service + a single read-only uint16
 * characteristic carrying battery voltage in millivolts. nRF Connect
 * will display this under "Unknown Service"; the ESS instance below
 * covers the recognised temperature and humidity values.
 */
BT_GATT_SERVICE_DEFINE(kclock_batt_svc,
    BT_GATT_PRIMARY_SERVICE(BT_UUID_DECLARE_128(kclock_batt_svc_uuid)),
    BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_128(kclock_batt_mv_uuid),
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           read_u16_cb, NULL, &last_batt_mV),
);

/* Static Environmental-Sensing-Service instance for temperature
 * and humidity, recognised by nRF Connect out of the box.
 */
static struct bt_es *ess_instance;

/* Single shared advertising record; the local-name record's length
 * is filled in once we know the address.
 */
static struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, local_name, 0),
};

/* Read callback for the battery-mV characteristic. */
static ssize_t read_u16_cb(struct bt_conn *conn,
                           const struct bt_gatt_attr *attr,
                           void *buf, uint16_t len, uint16_t offset)
{
    const uint16_t *value = (const uint16_t *)attr->user_data;
    return bt_gatt_attr_read(conn, attr, buf, len, offset,
                             value, sizeof(*value));
}

/* Connection lifecycle hooks — print only, no policy action. */
static void on_connected(struct bt_conn *conn, uint8_t err)
{
    if (err) {
        printk("BLE conn failed: 0x%02x\n", err);
        return;
    }
    char addr_str[BT_ADDR_LE_STR_LEN];
    bt_addr_le_to_str(bt_conn_get_dst(conn), addr_str, sizeof(addr_str));
    printk("BLE connected: %s (advertising as %s)\n", addr_str, local_name);
}

static void on_disconnected(struct bt_conn *conn, uint8_t reason)
{
    printk("BLE disconnected: reason 0x%02x\n", reason);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected    = on_connected,
    .disconnected = on_disconnected,
};

static void set_local_name_from_addr(const bt_addr_le_t *addr)
{
    uint8_t last_byte = addr->a.val[BT_ADDR_BYTES - 1];
    int n = snprintf(local_name, sizeof(local_name),
                     "kclock-%02x", last_byte);
    if (n > 0 && n < (int)sizeof(local_name)) {
        ad[1].data_len = (uint8_t)n;
    } else {
        ad[1].data_len = (uint8_t)(sizeof(local_name) - 1);
    }
}

int kclock_ble_init(void)
{
    int err;

    bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
    size_t        count = ARRAY_SIZE(addrs);
    err = bt_id_get(addrs, &count);
    if (err) {
        printk("bt_id_get failed: %d\n", err);
        return err;
    }

    set_local_name_from_addr(&addrs[0]);

    err = bt_enable(NULL);
    if (err) {
        printk("bt_enable failed: %d\n", err);
        return err;
    }

    err = bt_le_adv_start(BT_LE_ADV_CONN, ad, ARRAY_SIZE(ad), NULL, 0);
    if (err) {
        printk("bt_le_adv_start failed: %d\n", err);
        return err;
    }

    ess_instance = BT_ES_DEFINE(BT_UUID_ESS_TEMPERATURE,
                                BT_UUID_ESS_HUMIDITY);
    if (!ess_instance) {
        printk("BT_ES_DEFINE failed: %d\n", err);
        return -EIO;
    }

    printk("BLE ready: name=%s\n", local_name);
    for (size_t i = 0; i < count; i++) {
        if (addrs[i].type != BT_ADDR_LE_PUBLIC) {
            continue;
        }
        printk("BLE addr[%zu] = %02x:%02x:%02x:%02x:%02x:%02x\n",
               i,
               addrs[i].a.val[5], addrs[i].a.val[4], addrs[i].a.val[3],
               addrs[i].a.val[2], addrs[i].a.val[1], addrs[i].a.val[0]);
    }

    return 0;
}

void kclock_ble_set_readings(int16_t temp_centiC,
                             uint16_t hum_centi,
                             uint16_t batt_mV)
{
    /* ESS uses struct sensor_value .val1 = integer part,
     * .val2 = 1e-6 fractional part (fraction of the integer unit).
     * Convert centi-units to that representation.
     * For positive temps this is straightforward. For negative
     * temps the C99 truncating division gives the correct signed
     * integer part and remainder (e.g. -3.45 °C → val1 = -3,
     * val2 = -450_000).
     */
    struct sensor_value t = {
        .val1 = (int32_t)(temp_centiC / 100),
        .val2 = (int32_t)(temp_centiC % 100) * 10000,
    };
    struct sensor_value h = {
        .val1 = (int32_t)(hum_centi / 100),
        .val2 = (int32_t)(hum_centi % 100) * 10000,
    };

    if (ess_instance) {
        (void)bt_es_set_temperature(ess_instance, &t);
        (void)bt_es_set_humidity(ess_instance, &h);
    }
    last_batt_mV = batt_mV;
}

void kclock_ble_print_local_name(void)
{
    printk("BLE local-name: %s\n", local_name);
}
