use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}
pub fn secret() -> String {
    hex::encode(rand::random::<[u8; 32]>())
}
fn digest(value: &str) -> String {
    hex::encode(Sha256::digest(value.as_bytes()))
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Device {
    pub id: String,
    pub name: String,
    token_hash: String,
    pub paired_at: u64,
}
#[derive(Serialize, Deserialize)]
pub struct Pairing {
    pub instance: String,
    pub devices: Vec<Device>,
    #[serde(skip)]
    path: PathBuf,
    #[serde(skip)]
    ticket: Option<(String, u64)>,
}
impl Pairing {
    pub fn open(root: &Path) -> Result<Self, String> {
        let path = root.join("User_Data/mobile/pairing.json");
        let mut value: Self = if path.is_file() {
            serde_json::from_slice(&std::fs::read(&path).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?
        } else {
            Self {
                instance: secret(),
                devices: Vec::new(),
                path: path.clone(),
                ticket: None,
            }
        };
        value.path = path;
        value.save()?;
        Ok(value)
    }
    fn save(&self) -> Result<(), String> {
        std::fs::create_dir_all(self.path.parent().unwrap()).map_err(|e| e.to_string())?;
        let temp = self.path.with_extension("tmp");
        std::fs::write(&temp, serde_json::to_vec(self).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
        std::fs::rename(temp, &self.path).map_err(|e| e.to_string())
    }
    pub fn invite(&mut self, endpoint: &str, name: &str) -> Value {
        let token = secret();
        let expires = now() + 120_000;
        self.ticket = Some((token.clone(), expires));
        json!({"kind":"rvc-fabric-pairing","version":1,"endpoint":endpoint,"instance":self.instance,
            "name":name,"ticket":token,"expires_at":expires})
    }
    pub fn pair(&mut self, ticket: &str, id: &str, name: &str) -> Result<Value, String> {
        let valid = self
            .ticket
            .as_ref()
            .is_some_and(|(value, expires)| value == ticket && *expires > now());
        if !valid {
            return Err("pairing_expired".into());
        }
        if id.is_empty()
            || id.len() > 80
            || !id.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
        {
            return Err("invalid_device".into());
        }
        let name: String = name.chars().filter(|c| !c.is_control()).take(80).collect();
        if name.trim().is_empty() {
            return Err("invalid_device".into());
        }
        let token = secret();
        let old = self.devices.clone();
        self.devices.retain(|d| d.id != id);
        self.devices.push(Device {
            id: id.into(),
            name,
            token_hash: digest(&token),
            paired_at: now(),
        });
        if let Err(e) = self.save() {
            self.devices = old;
            return Err(e);
        }
        self.ticket = None;
        Ok(json!({"token":token,"instance":self.instance,"protocol":1}))
    }
    pub fn authorize(&self, token: &str) -> Option<Device> {
        if token.len() != 64 {
            return None;
        }
        let hash = digest(token);
        self.devices.iter().find(|d| d.token_hash == hash).cloned()
    }
    pub fn revoke(&mut self, id: &str) -> Result<(), String> {
        let old = self.devices.clone();
        self.devices.retain(|d| d.id != id);
        if let Err(e) = self.save() {
            self.devices = old;
            return Err(e);
        }
        Ok(())
    }
    pub fn public_devices(&self) -> Value {
        json!(self
            .devices
            .iter()
            .map(|d| json!({"id":d.id,"name":d.name,"paired_at":d.paired_at}))
            .collect::<Vec<_>>())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invitation_is_single_use_and_credentials_are_revocable() {
        let dir = std::env::temp_dir().join(format!("fabric-pair-{}", secret()));
        let mut store = Pairing::open(&dir).unwrap();
        let invite = store.invite("http://192.168.1.2:8787", "PC");
        let ticket = invite["ticket"].as_str().unwrap();
        let result = store.pair(ticket, "device-1", "Phone").unwrap();
        assert!(store.pair(ticket, "device-2", "Other").is_err());
        let token = result["token"].as_str().unwrap();
        assert!(store.authorize(token).is_some());
        assert!(!std::fs::read_to_string(&store.path)
            .unwrap()
            .contains(token));
        store.revoke("device-1").unwrap();
        assert!(Pairing::open(&dir).unwrap().authorize(token).is_none());
        std::fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn refresh_and_expiration_invalidate_previous_invite() {
        let mut store = Pairing {
            instance: secret(),
            devices: vec![],
            path: PathBuf::new(),
            ticket: None,
        };
        let old = store.invite("http://host:8787", "PC");
        store.invite("http://host:8787", "PC");
        assert!(store
            .pair(old["ticket"].as_str().unwrap(), "id", "Phone")
            .is_err());
        store.ticket = Some(("expired".into(), now() - 1));
        assert!(store.pair("expired", "id", "Phone").is_err());
    }
}
