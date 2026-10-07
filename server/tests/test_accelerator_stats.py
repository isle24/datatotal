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


class DevfreqParsingTests(unittest.TestCase):
    """ARM SoCs (Rockchip RK3588 class) only expose a devfreq governor load."""

    def test_parse_devfreq_load_reads_load_and_frequency(self):
        self.assertEqual(accelerator.parse_devfreq_load("0@300000000Hz"),
                         {"load": 0, "frequencyHz": 300000000})
        self.assertEqual(accelerator.parse_devfreq_load(" 250@1000000000Hz\n"),
                         {"load": 250, "frequencyHz": 1000000000})
        self.assertEqual(accelerator.parse_devfreq_load("17"), {"load": 17, "frequencyHz": None})
        self.assertIsNone(accelerator.parse_devfreq_load("busy"))
        self.assertIsNone(accelerator.parse_devfreq_load(""))

    def test_devfreq_utilization_scales_per_mille_and_clamps(self):
        self.assertEqual(accelerator.devfreq_utilization(0), 0.0)
        self.assertEqual(accelerator.devfreq_utilization(250), 25.0)
        self.assertEqual(accelerator.devfreq_utilization(1000), 100.0)
        self.assertEqual(accelerator.devfreq_utilization(5000), 100.0)
        self.assertIsNone(accelerator.devfreq_utilization(None))

    def test_match_devfreq_picks_the_matching_device(self):
        names = ["dmc", "fb000000.gpu", "fdab0000.npu", "fdd90000.vop"]
        self.assertEqual(accelerator.match_devfreq(names, "gpu"), "fb000000.gpu")
        self.assertEqual(accelerator.match_devfreq(names, "npu"), "fdab0000.npu")
        self.assertIsNone(accelerator.match_devfreq(names, "vpu"))

    def test_devfreq_device_describes_frequency_and_load(self):
        with tempfile.TemporaryDirectory() as root:
            device = Path(root) / "fb000000.gpu"
            device.mkdir()
            (device / "load").write_text("0@300000000Hz\n")
            (device / "cur_freq").write_text("300000000\n")
            (device / "min_freq").write_text("300000000\n")
            (device / "max_freq").write_text("900000000\n")
            (device / "governor").write_text("simple_ondemand\n")
            info = accelerator._DevfreqDevice(root, "fb000000.gpu").describe()
        self.assertEqual(info["driver"], "devfreq")
        self.assertEqual(info["utilPercent"], 0.0)
        self.assertEqual(info["loadRaw"], 0)
        self.assertEqual(info["frequencyMhz"], 300)
        self.assertEqual(info["maxFrequencyMhz"], 900)
        self.assertEqual(info["governor"], "simple_ondemand")

    def test_devfreq_device_hints_when_the_attribute_is_missing(self):
        with tempfile.TemporaryDirectory() as root:
            device = Path(root) / "fb000000.gpu"
            device.mkdir()
            info = accelerator._DevfreqDevice(root, "fb000000.gpu").describe()
        self.assertIsNone(info["utilPercent"])
        self.assertEqual(info["hint"], accelerator._HINT_NO_DEVFREQ)


class MppVpuTests(unittest.TestCase):
    """The Rockchip VPU reports ready-made percentages through MPP."""

    SAMPLE = (
        "fdb50400.vdpu             load:   0.00% utilization:   0.00%\n"
        "fdb50000.vepu             load:   0.00% utilization:   0.00%\n"
        "fdbd0000.rkvenc-core      load:  12.00% utilization:  34.50%\n"
        "fdc38100.rkvdec-core      load:  40.00% utilization:  62.25%\n"
        "fdc70000.av1d             load:   1.00% utilization:   2.00%\n"
        "\n"
        "not a core line\n"
    )

    def test_parse_mpp_load_reads_every_core(self):
        cores = accelerator.parse_mpp_load(self.SAMPLE)
        self.assertEqual(len(cores), 5)
        self.assertEqual(cores[0], {"device": "fdb50400.vdpu", "loadPercent": 0.0, "utilizationPercent": 0.0})
        self.assertEqual(cores[3]["device"], "fdc38100.rkvdec-core")
        self.assertEqual(cores[3]["utilizationPercent"], 62.25)
        self.assertEqual(accelerator.parse_mpp_load(""), [])
        self.assertEqual(accelerator.parse_mpp_load(None), [])

    def test_vpu_role_classifies_decode_and_encode_cores(self):
        self.assertEqual(accelerator.vpu_role("fdc38100.rkvdec-core"), "decode")
        self.assertEqual(accelerator.vpu_role("fdc70000.av1d"), "decode")
        self.assertEqual(accelerator.vpu_role("fdb50000.vepu"), "encode")
        self.assertEqual(accelerator.vpu_role("fdba0000.jpege-core"), "encode")
        self.assertEqual(accelerator.vpu_role("fdbb0000.iep"), "other")

    def test_mpp_summary_reports_peaks_per_role(self):
        summary = accelerator.mpp_summary(accelerator.parse_mpp_load(self.SAMPLE))
        self.assertEqual(summary["decodePercent"], 62.25)
        self.assertEqual(summary["encodePercent"], 34.5)
        self.assertEqual(summary["maxPercent"], 62.25)
        self.assertEqual(summary["coreCount"], 5)
        self.assertEqual(summary["activeCoreCount"], 3)
        self.assertEqual(accelerator.mpp_summary([])["maxPercent"], 0.0)

    def test_sampler_reads_vpu_cores_from_a_fake_proc_file(self):
        with tempfile.TemporaryDirectory() as root:
            load_file = Path(root) / "mpp_load"
            load_file.write_text(self.SAMPLE)
            sampler = accelerator.AcceleratorSampler(mpp_load_path=str(load_file))
            entries = sampler._sample_vpu()
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["name"], "Rockchip VPU")
        self.assertEqual(entry["utilPercent"], 62.25)
        self.assertEqual(entry["status"], "busy")
        self.assertEqual(entry["coreCount"], 5)
        self.assertEqual(entry["busiestCore"], "fdc38100.rkvdec-core")
        self.assertTrue(all(core["role"] for core in entry["cores"]))

    def test_sampler_stays_quiet_without_mpp(self):
        sampler = accelerator.AcceleratorSampler(mpp_load_path="/nonexistent/mpp/load")
        self.assertEqual(sampler._sample_vpu(), [])


class DevfreqBaselineTests(unittest.TestCase):
    """Idle Rockchip devices can report a fixed baseline instead of zero."""

    def _device(self, root, name, load, governor="rknpu_ondemand"):
        device = Path(root) / name
        device.mkdir(exist_ok=True)
        (device / "load").write_text(load)
        (device / "governor").write_text(governor)
        (device / "cur_freq").write_text("300000000\n")
        return device

    def test_idle_baseline_is_not_reported_as_utilization(self):
        with tempfile.TemporaryDirectory() as root:
            self._device(root, "fdab0000.npu", "100@300000000Hz\n")
            sampler = accelerator.AcceleratorSampler(devfreq_root=root)
            idle = sampler._devfreq_device("npu")
        self.assertEqual(idle["loadRaw"], 100)
        self.assertEqual(idle["loadBaseline"], 100)
        self.assertEqual(idle["utilPercent"], 0.0)

    def test_utilization_is_measured_above_the_baseline(self):
        with tempfile.TemporaryDirectory() as root:
            device = self._device(root, "fdab0000.npu", "100@300000000Hz\n")
            sampler = accelerator.AcceleratorSampler(devfreq_root=root)
            sampler._devfreq_device("npu")
            (device / "load").write_text("350@600000000Hz\n")
            busy = sampler._devfreq_device("npu")
        self.assertEqual(busy["loadBaseline"], 100)
        self.assertEqual(busy["utilPercent"], 25.0)
        self.assertEqual(busy["frequencyMhz"], 600)

    def test_zero_baseline_devices_keep_their_percentage(self):
        with tempfile.TemporaryDirectory() as root:
            device = self._device(root, "fb000000.gpu", "0@300000000Hz\n", "simple_ondemand")
            sampler = accelerator.AcceleratorSampler(devfreq_root=root)
            self.assertEqual(sampler._devfreq_device("gpu")["utilPercent"], 0.0)
            (device / "load").write_text("500@800000000Hz\n")
            busy = sampler._devfreq_device("gpu")
        self.assertEqual(busy["loadBaseline"], 0)
        self.assertEqual(busy["utilPercent"], 50.0)
