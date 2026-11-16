use crate::voices;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::path::Path;

pub fn id(path: &str) -> String {
    hex::encode(Sha256::digest(path.as_bytes()))[..24].into()
}
pub fn models(root: &Path) -> Vec<Value> {
    voices::list_voices(root)["models"].as_array().cloned().unwrap_or_default().into_iter()
        .filter(|v|!v["missing"].as_bool().unwrap_or(false)&&v["path"].as_str().is_some()).map(|mut v| {
            v["id"]=json!(id(v["path"].as_str().unwrap()));
            let profiles=voices::list_profiles(root,v["dir"].as_str().unwrap_or("")).unwrap_or_else(|_|json!({}));
            v["profiles"]=profiles["items"].as_array().map(|rows|json!(rows.iter().map(|p|json!({
                "id":if p["id"].as_str()==Some(""){"__default__"}else{p["id"].as_str().unwrap_or("")},"name":p["name"]
            })).collect::<Vec<_>>())).unwrap_or_else(||json!([{"id":"__default__","name":"Default"}]));
            v
        }).collect()
}
pub fn public(models: &[Value]) -> Value {
    json!(models
        .iter()
        .map(|m| json!({"id":m["id"],"name":m["name"],"profiles":m["profiles"]}))
        .collect::<Vec<_>>())
}
