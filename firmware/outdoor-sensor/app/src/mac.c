#include "mac.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

/* Print the public BLE address(es) to the console.
 *
 * In Zephyr 3.7 `bt_id_get()` returns 0 addresses until
 * `bt_enable()` has been called — the BT host stack populates the
 * identity table as part of controller init. Calling this before
 * `kclock_ble_init()` would print a misleading "zero addresses"
 * message; the function is kept as a thin wrapper for callers that
 * have already brought up the controller (e.g. for symmetry with
 * other diagnostics), but at the moment the BLE address is printed
 * from inside `kclock_ble_init()` itself, immediately after the
 * controller reports an identity count > 0.
 *
 * bt_id_get() in Zephyr 3.7 also returns `void` (instead of the
 * older `int` status code); output is delivered through the
 * pointers.
 */
void kclock_mac_print(void)
{
    bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
    size_t        count = ARRAY_SIZE(addrs);

    bt_id_get(addrs, &count);
    if (count == 0) {
        printk("MAC: 0 addresses (controller not yet initialised)\n");
        return;
    }

    for (size_t i = 0; i < count; i++) {
        if (addrs[i].type != BT_ADDR_LE_PUBLIC) {
            continue;
        }
        printk("MAC[%zu]: %02x:%02x:%02x:%02x:%02x:%02x\n",
               i,
               addrs[i].a.val[5], addrs[i].a.val[4], addrs[i].a.val[3],
               addrs[i].a.val[2], addrs[i].a.val[1], addrs[i].a.val[0]);
    }
}
