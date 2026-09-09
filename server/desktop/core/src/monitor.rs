use crate::{metrics::*, storage::Store, Result};
use std::{
    collections::BTreeMap,
    path::Path,
    sync::{
        atomic::{AtomicI64, Ordering},
        Arc, Condvar, Mutex,
    },
    thread,
    time::Duration,
};
use sysinfo::{Disks, Networks, ProcessRefreshKind, ProcessesToUpdate, System};

pub struct Monitor {
    pub store: Mutex<Store>,
    snapshot: Mutex<Snapshot>,
    process_until: AtomicI64,
    history_generation: AtomicI64,
    wake: (Mutex<bool>, Condvar),
    worker: Mutex<Option<thread::JoinHandle<()>>>,
}
impl Monitor {
    pub fn start(path: &Path) -> Result<Arc<Self>> {
        let monitor = Arc::new(Self {
            store: Mutex::new(Store::open(path)?),
            snapshot: Mutex::new(Snapshot::default()),
            process_until: AtomicI64::new(0),
            history_generation: AtomicI64::new(0),
            wake: (Mutex::new(false), Condvar::new()),
            worker: Mutex::new(None),
        });
        let worker = monitor.clone();
        *monitor.worker.lock().unwrap() = Some(
            thread::Builder::new()
                .name("local-sampler".into())
                .spawn(move || worker.run())
                .map_err(|e| e.to_string())?,
        );
        Ok(monitor)
    }
    pub fn snapshot(&self, processes: bool) -> Snapshot {
        if processes {
            self.process_until
                .store(chrono::Utc::now().timestamp() + 8, Ordering::Relaxed);
        }
        let mut result = self.snapshot.lock().unwrap().clone();
        if !processes {
            result.processes.clear();
        }
        result
    }
    pub fn stop(&self) {
        *self.wake.0.lock().unwrap() = true;
        self.wake.1.notify_all();
        if let Some(handle) = self.worker.lock().unwrap().take() {
            let _ = handle.join();
        }
    }
    pub fn clear_history(&self) -> Result<()> {
        let mut db = self.store.lock().unwrap();
        db.clear_history()?;
        self.history_generation.fetch_add(1, Ordering::SeqCst);
        Ok(())
    }
    fn run(&self) {
        let mut system = System::new();
        let mut processes = System::new();
        let mut networks = Networks::new_with_refreshed_list();
        let mut disks = Disks::new_with_refreshed_list();
        let mut meter = NetworkMeter::default();
        let mut pending = BTreeMap::<(i64, String), (u64, u64)>::new();
        let mut last_flush = 0;
        let mut last_disk = 0;
        let mut last_process = 0;
        let mut last_prune = 0;
        let mut generation = 0;
        system.refresh_cpu_usage();
        loop {
            let current = self.history_generation.load(Ordering::SeqCst);
            if current != generation {
                pending.clear();
                meter = NetworkMeter::default();
                generation = current;
            }
            let now = chrono::Utc::now().timestamp();
            networks.refresh(true);
            system.refresh_cpu_usage();
            system.refresh_memory();
            let interfaces = meter.update(
                now,
                networks
                    .iter()
                    .map(|(name, n)| (name.clone(), (n.total_received(), n.total_transmitted())))
                    .collect(),
            );
            for row in &interfaces {
                if row.rx_bytes + row.tx_bytes > 0 {
                    let entry = pending
                        .entry((now / 60 * 60, row.name.clone()))
                        .or_default();
                    entry.0 += row.rx_bytes;
                    entry.1 += row.tx_bytes;
                }
            }
            let mut error = None;
            if now - last_flush >= 30 {
                let rows: Vec<_> = pending
                    .iter()
                    .map(|((t, n), (r, w))| (*t, n.clone(), *r, *w))
                    .collect();
                let mut db = self.store.lock().unwrap();
                if generation != self.history_generation.load(Ordering::SeqCst) {
                    pending.clear();
                } else {
                    match db.write_batch(&rows) {
                        Ok(()) => pending.clear(),
                        Err(e) => error = Some(format!("历史写入失败：{e}")),
                    }
                }
                // Bound memory even when storage stays unavailable. Surface the loss explicitly.
                if pending.len() > 4096 {
                    pending.clear();
                    error = Some("存储持续不可用，已丢弃待写入历史".into());
                }
                last_flush = now;
            }
            if now - last_prune >= 3600 {
                let mut db = self.store.lock().unwrap();
                let days = db
                    .setting("retentionDays")
                    .ok()
                    .flatten()
                    .and_then(|v| v.as_i64())
                    .unwrap_or(30)
                    .clamp(1, 365);
                if let Err(e) = db.prune(now - days * 86400) {
                    error = Some(e);
                }
                last_prune = now;
            }
            if now - last_disk >= 60 {
                disks.refresh(true);
                last_disk = now;
            }
            let mut rows = Vec::new();
            let mut count = 0;
            if self.process_until.load(Ordering::Relaxed) >= now {
                processes.refresh_processes_specifics(
                    ProcessesToUpdate::All,
                    true,
                    ProcessRefreshKind::nothing()
                        .with_cpu()
                        .with_memory()
                        .with_disk_usage(),
                );
                let dt = (now - last_process).max(1) as f64;
                let baseline = last_process == 0 || now - last_process > 10;
                count = processes.processes().len();
                rows = processes
                    .processes()
                    .iter()
                    .map(|(pid, p)| {
                        let disk = p.disk_usage();
                        ProcessSample {
                            pid: pid.as_u32(),
                            started_at: p.start_time(),
                            name: p.name().to_string_lossy().into_owned(),
                            cpu_percent: if baseline {
                                0.0
                            } else {
                                p.cpu_usage() / system.cpus().len().max(1) as f32
                            },
                            memory_bytes: p.memory(),
                            read_bps: if baseline {
                                0.0
                            } else {
                                disk.read_bytes as f64 / dt
                            },
                            write_bps: if baseline {
                                0.0
                            } else {
                                disk.written_bytes as f64 / dt
                            },
                        }
                    })
                    .collect();
                last_process = now;
            } else if last_process != 0 {
                processes = System::new();
                last_process = 0;
            }
            *self.snapshot.lock().unwrap() = Snapshot {
                timestamp: now,
                host: System::host_name().unwrap_or_else(|| "本机".into()),
                os: System::long_os_version().unwrap_or_default(),
                cpu_name: system
                    .cpus()
                    .first()
                    .map(|c| c.brand().to_string())
                    .unwrap_or_default(),
                cpu_percent: system.global_cpu_usage(),
                cpu_count: system.cpus().len(),
                memory_bytes: system.used_memory(),
                total_memory_bytes: system.total_memory(),
                uptime: System::uptime(),
                interfaces,
                processes: rows,
                process_count: count,
                processes_at: last_process,
                disks: disks
                    .iter()
                    .map(|d| DiskSample {
                        name: d.name().to_string_lossy().into_owned(),
                        mount: d.mount_point().to_string_lossy().into_owned(),
                        total_bytes: d.total_space(),
                        available_bytes: d.available_space(),
                    })
                    .collect(),
                error,
            };
            let (stop, _) = self
                .wake
                .1
                .wait_timeout_while(
                    self.wake.0.lock().unwrap(),
                    Duration::from_secs(2),
                    |stop| !*stop,
                )
                .unwrap();
            if *stop {
                break;
            }
        }
        let rows = pending
            .into_iter()
            .map(|((t, n), (r, w))| (t, n, r, w))
            .collect::<Vec<_>>();
        let mut db = self.store.lock().unwrap();
        if generation == self.history_generation.load(Ordering::SeqCst) {
            if let Err(e) = db.write_batch(&rows) {
                eprintln!("history flush failed: {e}");
            }
        }
    }
}
