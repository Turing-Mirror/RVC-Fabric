//! One-time migration from the pre-1.6 root `Runtime/` tree.
//!
//! Migration is deliberately a move, not a download. The old tree stays in
//! place until the destination is ready, and the operation is idempotent so a
//! later version can recover from a process stopping between the move and the
//! config write.

use std::fs;
use std::path::Path;

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::{config, paths, provision, worker};

fn package_meta(root: &Path) -> Value {
    fs::read_to_string(paths::package_meta_path(root))
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_else(|| json!({}))
}

fn metadata_variant(root: &Path) -> Option<String> {
    let meta = package_meta(root);
    meta.get("variant")
        .or_else(|| meta.get("runtime_variant"))
        .and_then(|value| value.as_str())
        .and_then(paths::normalize_runtime_variant)
        .map(str::to_string)
}

fn metadata_label(root: &Path) -> String {
    let meta = package_meta(root);
    if let Some(label) = meta
        .get("label")
        .and_then(|value| value.as_str())
        .filter(|value| !value.trim().is_empty())
    {
        return label.to_string();
    }
    metadata_variant(root).unwrap_or_else(|| "nvidia".to_string())
}

fn metadata_version(root: &Path) -> String {
    package_meta(root)
        .get("runtime_version")
        .and_then(|value| value.as_str())
        .unwrap_or("")
        .trim()
        .to_string()
}

fn variant_options() -> Vec<Value> {
    [
        ("nvidia", crate::i18n::t("runtimeMigration.nvidia")),
        ("nvidia50", crate::i18n::t("runtimeMigration.nvidia50")),
        ("amd", crate::i18n::t("runtimeMigration.amd")),
    ]
    .into_iter()
    .map(|(id, label)| json!({ "id": id, "label": label }))
    .collect()
}

pub fn status(root: &Path) -> Value {
    let required = paths::runtime_migration_required(root);
    let legacy = paths::legacy_runtime_dir(root).is_some();
    let managed = paths::managed_runtime_variants(root);
    let variant = metadata_variant(root);
    let needs_variant = required
        && if legacy {
            variant.is_none()
        } else {
            managed.len() != 1
        };

    json!({
        "required": required,
        "needs_variant": needs_variant,
        "variant": variant,
        "version": metadata_version(root),
        "active_variant": paths::active_runtime_variant(root),
        "managed_variants": managed,
        "options": variant_options(),
    })
}

fn emit(app: &AppHandle, phase: &str, message: String, percent: u8) {
    let _ = app.emit(
        "runtime-migration-progress",
        json!({
            "phase": phase,
            "percent": percent,
            "message": message,
        }),
    );
}

/// Move the old Runtime tree into the selected managed variant directory.
pub fn run(
    app: AppHandle,
    root: &Path,
    requested_variant: Option<String>,
) -> Result<Value, String> {
    if !paths::runtime_migration_required(root) {
        emit(&app, "done", crate::i18n::t("runtimeMigration.done"), 100);
        return Ok(json!({ "ok": true, "migrated": false }));
    }

    let legacy = paths::legacy_runtime_dir(root);
    let known_variant = metadata_variant(root);
    let managed = paths::managed_runtime_variants(root);
    let requested = requested_variant
        .as_deref()
        .and_then(paths::normalize_runtime_variant)
        .map(str::to_string);
    let selected = requested
        .or(known_variant)
        .or_else(|| (managed.len() == 1).then(|| managed[0].clone()))
        .ok_or_else(|| crate::i18n::t("runtimeMigration.selectVariant"))?;

    if worker::is_worker_alive(root) {
        return Err(crate::i18n::t("runtimeMigration.stopEngine"));
    }

    let target = paths::runtime_variant_dir(root, &selected);
    if target.exists() {
        if !paths::runtime_variant_ready(root, &selected) {
            return Err(crate::i18n::te(
                "runtimeMigration.targetExists",
                &(target.display()),
            ));
        }
        provision::activate_runtime(root, &selected)?;
        emit(&app, "done", crate::i18n::t("runtimeMigration.done"), 100);
        return Ok(json!({
            "ok": true,
            "migrated": false,
            "variant": selected,
        }));
    }

    let source = legacy.ok_or_else(|| crate::i18n::t("runtimeMigration.notFound"))?;
    emit(
        &app,
        "prepare",
        crate::i18n::t("runtimeMigration.prepare"),
        10,
    );
    fs::create_dir_all(paths::runtimes_dir(root)).map_err(|e| e.to_string())?;
    emit(&app, "move", crate::i18n::t("runtimeMigration.moving"), 45);
    fs::rename(&source, &target).map_err(|e| {
        crate::i18n::tn(
            "s.90e6bba99d",
            &[&format!(
                "{} -> {}: {e}",
                source.display(),
                target.display()
            )],
        )
    })?;

    emit(
        &app,
        "verify",
        crate::i18n::t("runtimeMigration.verifying"),
        75,
    );
    if !paths::runtime_tree_ready(&target) {
        let _ = fs::rename(&target, &source);
        return Err(crate::i18n::t("runtimeMigration.verifyFailed"));
    }

    let label = metadata_label(root);
    let version = metadata_version(root);
    if let Err(error) = provision::write_runtime_meta_at(&target, &selected, &label, &version) {
        let _ = fs::rename(&target, &source);
        return Err(error);
    }
    config::set_runtime_variant(root, &selected)?;
    // Keep the existing root metadata as a compatibility mirror. It is not
    // used to choose the active tree once runtime_variant has been written.
    provision::write_package_meta(root, &selected, &label, &version)?;

    emit(&app, "done", crate::i18n::t("runtimeMigration.done"), 100);
    Ok(json!({
        "ok": true,
        "migrated": true,
        "variant": selected,
        "version": version,
    }))
}
