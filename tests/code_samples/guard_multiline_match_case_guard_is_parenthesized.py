# before:
class State: pass
new_state = State()
new_state.domain = "input_datetime"

if new_state.domain == "input_datetime":
    print("datetime")
elif (
    new_state.domain == "sensor"
    and new_state.attributes.get(EntityStateAttribute.DEVICE_CLASS)
    in (sensor.SensorDeviceClass.TIMESTAMP, sensor.SensorDeviceClass.UPTIME)
    and new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
):
    print("sensor")

# after:
class State: pass
new_state = State()
new_state.domain = "input_datetime"

match new_state.domain:
    case "input_datetime":
        print("datetime")
    case "sensor" if (new_state.attributes.get(EntityStateAttribute.DEVICE_CLASS)
        in (sensor.SensorDeviceClass.TIMESTAMP, sensor.SensorDeviceClass.UPTIME) and new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)):
        print("sensor")

# assume:

# trace:
# datetime
