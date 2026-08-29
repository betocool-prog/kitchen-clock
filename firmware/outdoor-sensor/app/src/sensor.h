#ifndef KCLOCK_SENSOR_H
#define KCLOCK_SENSOR_H

#include <stdint.h>

int kclock_sensor_init(void);
int kclock_sensor_read(int16_t *temp_centiC, uint16_t *hum_centi);
int kclock_sensor_read_battery_mV(uint16_t *mv);

#endif /* KCLOCK_SENSOR_H */
