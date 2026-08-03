from textwrap import dedent

from matchify.transform import transform_code


def test_multiline_match_case_guard_is_parenthesized():
    source = dedent("""
        if new_state.domain == "input_datetime":
            print("datetime")
        elif (
            new_state.domain == "sensor"
            and new_state.attributes.get(EntityStateAttribute.DEVICE_CLASS)
            in (sensor.SensorDeviceClass.TIMESTAMP, sensor.SensorDeviceClass.UPTIME)
            and new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
        ):
            print("sensor")
        """).strip()

    expected = dedent("""
        match new_state.domain:
            case "input_datetime":
                print("datetime")
            case "sensor" if (new_state.attributes.get(EntityStateAttribute.DEVICE_CLASS)
                in (sensor.SensorDeviceClass.TIMESTAMP, sensor.SensorDeviceClass.UPTIME) and new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)):
                print("sensor")
        """).strip()

    assert transform_code(source).strip() == expected
    compile(expected, "<test>", "exec")
