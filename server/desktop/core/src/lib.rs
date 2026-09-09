pub mod metrics;
pub mod monitor;
pub mod nas;
pub mod storage;

pub type Result<T> = std::result::Result<T, String>;

#[cfg(test)]
mod tests;
