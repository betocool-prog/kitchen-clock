#ifndef KCLOCK_SENSOR_H
#define KCLOCK_SENSOR_H

#include <stdint.h>

int kclock_sensor_init(void);
int kclock_sensor_read(int16_t *temp_centiC, uint16_t *hum_centi);
int kclock_sensor_read_battery_mv(uint16_t *mv_out);

#endif /* KCLOCK_SENSOR_H */
