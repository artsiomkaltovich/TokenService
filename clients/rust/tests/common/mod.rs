use std::env;
use std::time::Duration;
use token_service_client::{TokenServiceError, UserId};
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UserUuid(pub Uuid);

impl UserId for UserUuid {
    fn to_bytes(&self) -> Vec<u8> {
        self.0.as_bytes().to_vec()
    }

    fn from_bytes(bytes: &[u8]) -> Result<Self, TokenServiceError> {
        let array: [u8; 16] = bytes
            .try_into()
            .map_err(|_| TokenServiceError::InvalidTokenFormat)?;
        Ok(UserUuid(Uuid::from_bytes(array)))
    }
}

pub const DEFAULT_TOXIPROXY_IMAGE: &str = "shopify/toxiproxy:2.1.4";
pub const DEFAULT_REDIS_IMAGE: &str = "redis:8-alpine";
pub const DEFAULT_TOKEN_IMAGE: &str = "tokenservice:local";

pub fn test_user_id() -> UserUuid {
    UserUuid(Uuid::parse_str("936da01f-9abd-4d9d-80c7-02af85c822a8").expect("valid uuid"))
}

pub fn server_url() -> String {
    env::var("TOKEN_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:5111".to_string())
}

pub fn toxiproxy_grpc_listen_port() -> u16 {
    env::var("TOXIPROXY_GRPC_LISTEN_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(15111)
}

pub fn toxiproxy_redis_listen_port() -> u16 {
    env::var("TOXIPROXY_REDIS_LISTEN_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(15112)
}

#[derive(Debug, serde::Serialize, serde::Deserialize, Clone)]
pub struct Proxy {
    pub name: String,
    pub listen: String,
    pub upstream: String,
    #[serde(default)]
    pub enabled: bool,
}

#[derive(Debug)]
pub struct ProxyGuard {
    client: reqwest::Client,
    pub proxy: Proxy,
    pub api_base: String,
}

impl ProxyGuard {
    pub fn new(client: reqwest::Client, proxy: Proxy, api_base: impl Into<String>) -> Self {
        Self {
            client,
            proxy,
            api_base: api_base.into(),
        }
    }

    pub fn name(&self) -> &str {
        &self.proxy.name
    }
}

impl Drop for ProxyGuard {
    fn drop(&mut self) {
        let url = format!("{}/proxies/{}", self.api_base, self.proxy.name);
        if let Ok(handle) = tokio::runtime::Handle::try_current() {
            tokio::task::block_in_place(|| {
                handle.block_on(async move {
                    dbg!(11111);
                    let _ = self.client.delete(&url).send();
                });
            });
        }
    }
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct CreateProxyPayload {
    pub name: String,
    pub listen: String,
    pub upstream: String,
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct ToxicAttributes {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub latency: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub jitter: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeout: Option<u32>,
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct ToxicPayload {
    pub name: String,
    #[serde(rename = "type")]
    pub toxic_type: String,
    pub stream: String,
    pub attributes: ToxicAttributes,
}

pub struct ToxiproxyApi {
    client: reqwest::Client,
}

impl Default for ToxiproxyApi {
    fn default() -> Self {
        Self::new()
    }
}

impl ToxiproxyApi {
    pub fn new() -> Self {
        Self {
            client: reqwest::Client::new(),
        }
    }

    pub async fn create_proxy(
        &self,
        api_base: &str,
        name: &str,
        upstream_host: &str,
        upstream_port: u16,
        listen_port: u16,
    ) -> Result<ProxyGuard, reqwest::Error> {
        let payload = CreateProxyPayload {
            name: name.to_string(),
            listen: format!("0.0.0.0:{}", listen_port),
            upstream: format!("{}:{}", upstream_host, upstream_port),
        };
        let res = self
            .client
            .post(format!("{}/proxies", api_base))
            .json(&payload)
            .send()
            .await?;
        res.error_for_status_ref()?;
        let proxy = res.json::<Proxy>().await?;
        Ok(ProxyGuard::new(self.client.clone(), proxy, api_base))
    }

    pub async fn delete_proxy(&self, api_base: &str, proxy_name: &str) {
        let _ = self
            .client
            .delete(format!("{}/proxies/{}", api_base, proxy_name))
            .send()
            .await;
    }

    pub async fn add_latency(
        &self,
        api_base: &str,
        proxy_name: &str,
        latency_ms: u32,
        toxic_name: Option<&str>,
    ) -> Result<(), reqwest::Error> {
        let payload = ToxicPayload {
            name: toxic_name.unwrap_or("latency").to_string(),
            toxic_type: "latency".to_string(),
            stream: "downstream".to_string(),
            attributes: ToxicAttributes {
                latency: Some(latency_ms),
                jitter: Some(0),
                timeout: None,
            },
        };
        let res = self
            .client
            .post(format!("{}/proxies/{}/toxics", api_base, proxy_name))
            .json(&payload)
            .send()
            .await?;
        res.error_for_status_ref()?;
        Ok(())
    }

    pub async fn add_timeout_toxic(
        &self,
        api_base: &str,
        proxy_name: &str,
        timeout_ms: u32,
        toxic_name: Option<&str>,
    ) -> Result<(), reqwest::Error> {
        let payload = ToxicPayload {
            name: toxic_name.unwrap_or("timeout").to_string(),
            toxic_type: "timeout".to_string(),
            stream: "downstream".to_string(),
            attributes: ToxicAttributes {
                latency: None,
                jitter: None,
                timeout: Some(timeout_ms),
            },
        };
        let res = self
            .client
            .post(format!("{}/proxies/{}/toxics", api_base, proxy_name))
            .json(&payload)
            .send()
            .await?;
        res.error_for_status_ref()?;
        Ok(())
    }

    pub async fn remove_toxic(&self, api_base: &str, proxy_name: &str, toxic_name: &str) {
        let _ = self
            .client
            .delete(format!(
                "{}/proxies/{}/toxics/{}",
                api_base, proxy_name, toxic_name
            ))
            .send()
            .await;
    }
}

pub struct TokenServiceAttrs {
    pub internal_host: String,
    pub internal_port: u16,
    pub host: String,
    pub host_port: u16,
}

impl TokenServiceAttrs {
    pub fn internal_url(&self) -> String {
        format!("{}:{}", self.internal_host, self.internal_port)
    }

    pub fn host_url(&self) -> String {
        format!("{}:{}", self.host, self.host_port)
    }
}

pub struct ToxiproxyContainerAttrs {
    pub api_base: String,
    pub host: String,
    pub mapped_ports: std::collections::HashMap<u16, u16>,
}

impl ToxiproxyContainerAttrs {
    pub fn map_listen_port(&self, listen_port: u16) -> u16 {
        *self.mapped_ports.get(&listen_port).unwrap_or(&listen_port)
    }
}

pub struct RedisContainerAttrs {
    pub host: String,
    pub port: u16,
}

pub async fn simulate_service_reconnect(
    toxiproxy_api: &ToxiproxyApi,
    api_base: &str,
    proxy_name: &str,
    target_name: &str,
    target_port: u16,
    listen_port: u16,
    down_time: Duration,
    old_guard: ProxyGuard,
) -> ProxyGuard {
    drop(old_guard);
    tokio::time::sleep(down_time).await;
    toxiproxy_api
        .create_proxy(api_base, proxy_name, target_name, target_port, listen_port)
        .await
        .expect("Failed to recreate Toxiproxy proxy")
}
