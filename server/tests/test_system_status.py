from collections import namedtuple
from pathlib import Path
import sys
import unittest
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


class ArmThermalZoneTests(unittest.TestCase):
    """Rockchip/RK3588 boards report per-cluster thermal zones."""

    def test_arm_thermal_zones_get_friendly_names(self):
        expected = {
            "soc_thermal": "SoC",
            "center_thermal": "SoC 中心",
            "gpu_thermal": "GPU",
            "npu_thermal": "NPU",
            "ddr_thermal": "内存",
            "vepu_thermal": "VPU 编码",
            "vdec_thermal": "VPU 解码",
        }
        for raw, label in expected.items():
            self.assertEqual(system_status.friendly_temperature_group(raw, 1), label, raw)

    def test_arm_cpu_clusters_keep_their_index(self):
        self.assertEqual(system_status.friendly_temperature_group("bigcore0_thermal", 1), "CPU 大核 0")
        self.assertEqual(system_status.friendly_temperature_group("bigcore1_thermal", 2), "CPU 大核 1")
        self.assertEqual(system_status.friendly_temperature_group("littlecore_thermal", 1), "CPU 小核")

    def test_unknown_thermal_suffix_falls_back_to_a_readable_name(self):
        self.assertEqual(system_status.friendly_temperature_group("gpu2_thermal", 1), "Gpu2")
        self.assertEqual(system_status.arm_temperature_group("coretemp"), None)

    def test_intel_names_still_win_over_the_arm_fallback(self):
        self.assertEqual(system_status.friendly_temperature_group("coretemp", 1), "CPU")
        self.assertEqual(system_status.friendly_temperature_group("acpitz", 1), "主板/机箱")
        self.assertEqual(system_status.friendly_temperature_group("nvme", 2), "NVMe 2")
