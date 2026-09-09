// Optional read-only connectivity check. Password is read from stdin, never from an argument.
use std::io;
use traffic_lens_core::{
    nas::{ApiRequest, NasClient, Packet},
    storage::Profile,
};

#[tokio::main]
async fn main() -> Result<(), String> {
    let url = std::env::args()
        .nth(1)
        .ok_or("Usage: nas_probe http(s)://host:port")?;
    let mut password = String::new();
    io::stdin()
        .read_line(&mut password)
        .map_err(|e| e.to_string())?;
    let profile = Profile {
        id: format!("probe-{}", uuid::Uuid::new_v4()),
        name: "Read-only probe".into(),
        url,
    };
    let id = profile.id.clone();
    let client = NasClient::default();
    client
        .login(
            profile,
            Some(password.trim_end_matches(['\r', '\n']).to_string()),
            false,
        )
        .await?;
    password.clear();
    let result = client
        .request(
            ApiRequest {
                profile_id: id.clone(),
                request_id: uuid::Uuid::new_v4().to_string(),
                path: "/api/overview".into(),
                method: "GET".into(),
                body: None,
            },
            |packet| {
                if let Packet::Headers { status } = packet {
                    println!("Read-only overview HTTP {status}");
                    if status != 200 {
                        return Err(format!("Unexpected status {status}"));
                    }
                }
                Ok(())
            },
        )
        .await;
    client.logout(&id).await?;
    result?;
    println!("Login, overview and logout completed. No NAS settings changed.");
    Ok(())
}
