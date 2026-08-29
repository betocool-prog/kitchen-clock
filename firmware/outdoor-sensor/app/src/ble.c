#include "ble.h"

#include <zephyr/bluetooth/addr.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>
#include <errno.h>
#include <string.h>

/*
 * Local-name format: "kclock-AB" where AB is the last byte of
 * the public BLE address rendered as two hex digits.
 */
#define KCLOCK_LOCAL_NAME_MAX  sizeof("kclock-XXXX")

/*
 * Custom 128-bit service UUID. The first four bytes spell "kclk"
 * (0x6b 0x63 0x6c 0x6b) so they are recognisable in a hex dump.
 *
 *   Service:        6b 63 6c 6b - 00 01 - 00 00 -
 *                   00 00 - 00 00 00 00 00 01
 *   Battery mV:     6b 63 6c 6b - 00 01 - 00 00 -
 *                   00 00 - 00 00 00 00 00 02
 *
 * Temperature and Humidity share the same primary service but use
 * the standard Bluetooth SIG Environmental-Sensing-Service
 * characteristic UUIDs (0x2A6E, 0x2A6F) so any BLE scanner
 * recognises them. Their encodings follow the SIG specification:
 * int16 at 0.01 °C, uint16 at 0.01 %RH. The "centi" values from
 * kclock_sensor_read() are a direct drop-in for those encodings.
 *
 * We declare the 128-bit UUID structs directly (instead of via
 * BT_UUID_DECLARE_128) because in Zephyr 3.7 that macro produces a
 * compound literal that GCC 12 treats as a non-constant
 * initializer inside the static BT_GATT_SERVICE_DEFINE block.
 */
static const struct bt_uuid_128 kclock_svc_uuid = {
    .uuid = { .type = BT_UUID_TYPE_128 },
    .val = {
        0x6b, 0x63, 0x6c, 0x6b, 0x00, 0x01, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01
    }
};
static const struct bt_uuid_128 kclock_batt_mv_uuid = {
    .uuid = { .type = BT_UUID_TYPE_128 },
    .val = {
        0x6b, 0x63, 0x6c, 0x6b, 0x00, 0x01, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02
    }
};

static char         local_name[KCLOCK_LOCAL_NAME_MAX];
static int16_t      last_temp_centi;
static uint16_t     last_hum_centi;
static uint16_t     last_batt_mV;

static ssize_t read_temp_cb(struct bt_conn *conn,
                            const struct bt_gatt_attr *attr,
                            void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset,
                             &last_temp_centi, sizeof(last_temp_centi));
}

static ssize_t read_hum_cb(struct bt_conn *conn,
                           const struct bt_gatt_attr *attr,
                           void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset,
                             &last_hum_centi, sizeof(last_hum_centi));
}

static ssize_t read_batt_cb(struct bt_conn *conn,
                            const struct bt_gatt_attr *attr,
                            void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset,
                             &last_batt_mV, sizeof(last_batt_mV));
}

BT_GATT_SERVICE_DEFINE(kclock_svc,
    BT_GATT_PRIMARY_SERVICE(&kclock_svc_uuid.uuid),
    BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_16(0x2A6E),
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           read_temp_cb, NULL, &last_temp_centi),
    BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_16(0x2A6F),
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           read_hum_cb, NULL, &last_hum_centi),
    BT_GATT_CHARACTERISTIC(&kclock_batt_mv_uuid.uuid,
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           read_batt_cb, NULL, &last_batt_mV),
);

static struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, local_name, 0),
};

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
    /* BT_ADDR_SIZE defined in <zephyr/bluetooth/addr.h>; = 6. */
    uint8_t last_byte = addr->a.val[BT_ADDR_SIZE - 1];
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

    /* In Zephyr 3.7 `bt_id_get()` only returns valid addresses AFTER
     * `bt_enable()` has finished initialising the controller. So
     * the order is: enable, then read addresses, then name, then
     * advertise. Calling bt_id_get before bt_enable returns 0
     * addresses, even though there is no fault — it just has not
     * been told anything yet.
     */
    err = bt_enable(NULL);
    if (err) {
        printk("bt_enable failed: %d\n", err);
        return err;
    }

    bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
    size_t        count = ARRAY_SIZE(addrs);

    bt_id_get(addrs, &count);
    if (count == 0) {
        printk("bt_id_get: controller initialised but 0 identities "
               "(check CONFIG_BT_ID_MAX and FICR.NRF_FICR_DEVICEADDR<n>)\n");
        return -ENODEV;
    }

    set_local_name_from_addr(&addrs[0]);

    err = bt_le_adv_start(BT_LE_ADV_CONN, ad, ARRAY_SIZE(ad), NULL, 0);
    if (err) {
        printk("bt_le_adv_start failed: %d\n", err);
        return err;
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
    last_temp_centi = temp_centiC;
    last_hum_centi  = hum_centi;
    last_batt_mV    = batt_mV;
}

void kclock_ble_print_local_name(void)
{
    printk("BLE local-name: %s\n", local_name);
}
