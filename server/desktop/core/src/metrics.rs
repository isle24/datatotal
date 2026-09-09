use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Clone, Default, Serialize)]
pub struct InterfaceSample {
    pub name: String,
    pub kind: String,
    pub rx_bytes: u64,
    pub tx_bytes: u64,
    pub rx_bps: f64,
    pub tx_bps: f64,
    pub system_rx_bytes: u64,
    pub system_tx_bytes: u64,
}

#[derive(Default)]
pub struct NetworkMeter {
    previous: BTreeMap<String, (u64, u64)>,
    timestamp: Option<i64>,
}

impl NetworkMeter {
    pub fn update(
        &mut self,
        now: i64,
        counters: BTreeMap<String, (u64, u64)>,
    ) -> Vec<InterfaceSample> {
        let dt = self.timestamp.map(|last| now - last).unwrap_or(0);
        let rows = counters
            .iter()
            .map(|(name, &(rx, tx))| {
                let (drx, dtx) = match self.previous.get(name) {
                    Some(&(old_rx, old_tx))
                        if (1..=15).contains(&dt) && rx >= old_rx && tx >= old_tx =>
                    {
                        (rx - old_rx, tx - old_tx)
                    }
                    _ => (0, 0),
                };
                let kind = if name.starts_with("lo") {
                    "loopback"
                } else if [
                    "utun", "tun", "tap", "bridge", "veth", "docker", "awdl", "llw", "anpi", "gif",
                    "stf",
                ]
                .iter()
                .any(|prefix| name.starts_with(prefix))
                {
                    "virtual"
                } else {
                    "interface"
                };
                InterfaceSample {
                    name: name.clone(),
                    kind: kind.into(),
                    rx_bytes: drx,
                    tx_bytes: dtx,
                    rx_bps: drx as f64 / dt.max(1) as f64,
                    tx_bps: dtx as f64 / dt.max(1) as f64,
                    system_rx_bytes: rx,
                    system_tx_bytes: tx,
                }
            })
            .collect();
        self.previous = counters;
        self.timestamp = Some(now);
        rows
    }
}

#[derive(Clone, Serialize)]
pub struct ProcessSample {
    pub pid: u32,
    pub started_at: u64,
    pub name: String,
    pub cpu_percent: f32,
    pub memory_bytes: u64,
    pub read_bps: f64,
    pub write_bps: f64,
}

#[derive(Clone, Serialize)]
pub struct DiskSample {
    pub name: String,
    pub mount: String,
    pub total_bytes: u64,
    pub available_bytes: u64,
}

#[derive(Clone, Default, Serialize)]
pub struct Snapshot {
    pub timestamp: i64,
    pub host: String,
    pub os: String,
    pub cpu_name: String,
    pub cpu_percent: f32,
    pub cpu_count: usize,
    pub memory_bytes: u64,
    pub total_memory_bytes: u64,
    pub uptime: u64,
    pub interfaces: Vec<InterfaceSample>,
    pub processes: Vec<ProcessSample>,
    pub process_count: usize,
    pub processes_at: i64,
    pub disks: Vec<DiskSample>,
    pub error: Option<String>,
}
