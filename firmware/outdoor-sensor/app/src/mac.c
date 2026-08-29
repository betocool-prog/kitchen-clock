#include "mac.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

/* Print the public BLE address(es) to the console. Used at boot so
 * the deployer can record each unit's MAC into the Pi's config.toml.
 *
 * Zephyr 3.7 changed bt_id_get() to return void: it writes its
 * outputs via the pointers and cannot fail in the way the older
 * int-returning API did.
 */
void kclock_mac_print(void)
{
    bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
    size_t        count = ARRAY_SIZE(addrs);

    bt_id_get(addrs, &count);
    if (count == 0) {
        printk("bt_id_get: zero addresses\n");
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
