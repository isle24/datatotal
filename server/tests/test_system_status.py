from collections import namedtuple
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.services import system_status


FanReading = namedtuple("FanReading", "label current")


def test_read_fan_stats_returns_every_sensor_with_friendly_names():
    readings = {
        "nct6798": [
            FanReading("CPU Fan", 3330),
            FanReading("System Fan", 879),
        ]
    }
    with patch.object(system_status.psutil, "sensors_fans", return_value=readings, create=True):
        fans = system_status.read_fan_stats()

    assert [item["name"] for item in fans] == ["CPU 风扇", "系统风扇"]
    assert [item["rpm"] for item in fans] == [3330, 879]
    assert all(item["status"] == "running" for item in fans)
    assert fans[0]["rawName"] == "nct6798"
    assert fans[0]["rawLabel"] == "CPU Fan"


def test_read_fan_stats_keeps_zero_speed_and_handles_missing_sensor_api():
    with patch.object(
        system_status.psutil,
        "sensors_fans",
        return_value={"hwmon": [FanReading("fan1", 0), FanReading("fan2", None)]},
        create=True,
    ):
        fans = system_status.read_fan_stats()
    assert len(fans) == 1
    assert fans[0]["rpm"] == 0
    assert fans[0]["status"] == "stopped"

    with patch.object(system_status.psutil, "sensors_fans", side_effect=OSError("not supported"), create=True):
        assert system_status.read_fan_stats() == []


def test_fan_label_fallback_distinguishes_multiple_generic_fans():
    readings = {"hwmon": [FanReading("fan1", 900), FanReading("fan2", 1000)]}
    with patch.object(system_status.psutil, "sensors_fans", return_value=readings, create=True):
        fans = system_status.read_fan_stats()
    assert [item["name"] for item in fans] == ["风扇 1", "风扇 2"]


if __name__ == "__main__":
    test_read_fan_stats_returns_every_sensor_with_friendly_names()
    test_read_fan_stats_keeps_zero_speed_and_handles_missing_sensor_api()
    test_fan_label_fallback_distinguishes_multiple_generic_fans()
    print("system status fan tests passed")
