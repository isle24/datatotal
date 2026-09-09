use base64::{engine::general_purpose::STANDARD, Engine};
use minisign_verify::{PublicKey, Signature};
use std::{env, fs};

fn main() -> std::result::Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 4 {
        return Err("Usage: verify_update <tauri.conf.json> <package> <signature>".into());
    }
    let config: serde_json::Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let key = String::from_utf8(
        STANDARD.decode(
            config["plugins"]["updater"]["pubkey"]
                .as_str()
                .ok_or("Missing public key")?,
        )?,
    )?;
    let signature = String::from_utf8(STANDARD.decode(fs::read_to_string(&args[3])?.trim())?)?;
    PublicKey::decode(&key)?.verify(&fs::read(&args[2])?, &Signature::decode(&signature)?, true)?;
    println!("Verified update signature: {}", args[2]);
    Ok(())
}
