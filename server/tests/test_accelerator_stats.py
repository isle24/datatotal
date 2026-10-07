import os
import tempfile
import unittest
from pathlib import Path

from server.services import accelerator_stats as accelerator


class PerfParsingTests(unittest.TestCase):
    def test_parse_perf_config_reads_hex_config(self):
        self.assertEqual(accelerator.parse_perf_config("config=0x2000"), 0x2000)
        self.assertEqual(accelerator.parse_perf_config("event=0x1,config=0x10"), 0x10)
        self.assertIsNone(accelerator.parse_perf_config("event=0x1"))
        self.assertIsNone(accelerator.parse_perf_config("config=zz"))
        self.assertIsNone(accelerator.parse_perf_config(None))

    def test_busy_percent_normalizes_by_enabled_time(self):
        previous = (0, 1_000_000_000, 1_000_000_000)
        self.assertEqual(accelerator.busy_percent(previous, (500_000_000, 2_000_000_000, 2_000_000_000)), 50.0)
        self.assertEqual(accelerator.busy_percent(previous, (2_000_000_000, 2_000_000_000, 2_000_000_000)), 100.0)
        # No elapsed enabled time, or a counter reset, must not produce a value.
        self.assertIsNone(accelerator.busy_percent(previous, (10, 1_000_000_000, 1_000_000_000)))
        self.assertIsNone(accelerator.busy_percent((100, 1_000_000_000, 1_000_000_000), (5, 2_000_000_000, 2_000_000_000)))

    def test_counter_percent_uses_microsecond_counters(self):
        # First read only establishes the baseline.
        self.assertIsNone(accelerator.counter_percent(None, None, 1000.0, 10.0, 1_000_000.0))
        # 500 ms of NPU busy time inside a 2 s window is 25 %.
        self.assertEqual(accelerator.counter_percent(1000.0, 10.0, 501_000.0, 12.0, 1_000_000.0), 25.0)
        self.assertEqual(accelerator.counter_percent(0.0, 10.0, 2_000_000.0, 12.0, 1_000_000.0), 100.0)
        self.assertEqual(accelerator.counter_percent(1000.0, 10.0, 1000.0, 12.0, 1_000_000.0), 0.0)
        # A zero-length window cannot be turned into a percentage.
        self.assertIsNone(accelerator.counter_percent(1000.0, 10.0, 1_000_000.0, 10.0, 1_000_000.0))
        self.assertIsNone(accelerator.counter_percent(2000.0, 10.0, 10.0, 12.0, 1_000_000.0))


class FakeSysfsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="accelerator-test-"))
        self.drm = self.root / "drm"
        self.accel = self.root / "accel"
        self.pmu = self.root / "pmu"
        self.drm.mkdir()
        self.accel.mkdir()
        self.pmu.mkdir()

    def _fake_card(self, driver="i915", with_busy_percent=None):
        card = self.drm / "card0"
        (card / "device").mkdir(parents=True)
        (card / "gt" / "gt0").mkdir(parents=True)
        (card / "gt" / "gt0" / "rps_act_freq_mhz").write_text("1200\n")
        (card / "gt" / "gt0" / "rc6_residency_ms").write_text("5000\n")
        driver_dir = self.root / "drivers" / driver
        driver_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(driver_dir, card / "device" / "driver")
        if with_busy_percent is not None:
            (card / "device" / "gpu_busy_percent").write_text(f"{with_busy_percent}\n")
        return card

    def _fake_npu(self, busy_us=0, memory=68722688, current=0, maximum=1400):
        device = self.accel / "accel0" / "device"
        device.mkdir(parents=True)
        (device / "npu_busy_time_us").write_text(f"{busy_us}\n")
        (device / "npu_memory_utilization").write_text(f"{memory}\n")
        (device / "npu_current_frequency_mhz").write_text(f"{current}\n")
        (device / "npu_max_frequency_mhz").write_text(f"{maximum}\n")
        (device / "power_state").write_text("D3hot\n")
        (device / "sched_mode").write_text("OS\n")
        return device

    def _sampler(self):
        return accelerator.AcceleratorSampler(
            drm_root=str(self.drm), accel_root=str(self.accel), pmu_root=str(self.pmu),
            interval=0.05, first_sample_seconds=0.01,
        )

    def test_missing_pmu_reports_a_hint_instead_of_a_percentage(self):
        self._fake_card()
        sampler = self._sampler()
        try:
            snapshot = sampler.snapshot()
        finally:
            sampler.stop()
        gpu = snapshot["gpus"][0]
        self.assertEqual(gpu["driver"], "i915")
        self.assertEqual(gpu["frequencyMhz"], 1200)
        self.assertIsNone(gpu["utilPercent"])
        self.assertIn("i915 PMU", gpu["hint"])

    def test_amdgpu_uses_the_driver_percentage(self):
        self._fake_card(driver="amdgpu", with_busy_percent=37)
        sampler = self._sampler()
        try:
            snapshot = sampler.snapshot()
        finally:
            sampler.stop()
        gpu = snapshot["gpus"][0]
        self.assertEqual(gpu["utilPercent"], 37.0)
        self.assertEqual(gpu["status"], "busy")
        self.assertEqual(gpu["hint"], "")

    def test_npu_reports_busy_time_frequency_and_memory(self):
        self._fake_npu(busy_us=2500000, current=900)
        sampler = self._sampler()
        try:
            sampler.snapshot()
            npu = sampler.snapshot()["npus"][0]
        finally:
            sampler.stop()
        self.assertEqual(npu["name"], "Intel NPU")
        self.assertEqual(npu["busyTimeUs"], 2500000)
        self.assertEqual(npu["memoryBytes"], 68722688)
        self.assertEqual(npu["frequencyMhz"], 900)
        self.assertEqual(npu["maxFrequencyMhz"], 1400)
        self.assertEqual(npu["powerState"], "D3hot")
        self.assertIsNotNone(npu["utilPercent"])

    def test_npu_counter_delta_is_a_percentage_of_the_window(self):
        device = self._fake_npu(busy_us=1000)
        counter = accelerator._NpuCounter(str(device))
        self.assertIsNone(counter.sample(10.0))
        (device / "npu_busy_time_us").write_text("1501000\n")
        self.assertEqual(counter.sample(12.0), 75.0)


if __name__ == "__main__":
    unittest.main()
