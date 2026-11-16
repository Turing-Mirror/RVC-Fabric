//! Persistent serial training jobs. The existing worker remains the execution contract.
use crate::train::{self, TrainReq};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    path::{Path, PathBuf},
    sync::{Mutex, OnceLock},
};
use tauri::{AppHandle, Emitter};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum State {
    Queued,
    Running,
    Cancelling,
    Paused,
    Interrupted,
    Completed,
    Failed,
    Cancelled,
}
impl State {
    fn active(&self) -> bool {
        matches!(
            self,
            Self::Queued | Self::Running | Self::Cancelling | Self::Paused
        )
    }
    fn terminal(&self) -> bool {
        !self.active()
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
struct Job {
    id: String,
    req: TrainReq,
    state: State,
    #[serde(default)]
    progress: Value,
    #[serde(default)]
    error: String,
    #[serde(default)]
    result: Value,
    /// Freeze the selected compute backend with the request. Audio remains in place.
    device: String,
}
#[derive(Clone, Default, Serialize, Deserialize)]
struct Queue {
    #[serde(default)]
    next_id: u64,
    #[serde(default)]
    jobs: Vec<Job>,
    #[serde(skip)]
    root: PathBuf,
    #[serde(skip)]
    dispatching: bool,
}
static QUEUE: OnceLock<Mutex<Option<Queue>>> = OnceLock::new();
fn lock() -> std::sync::MutexGuard<'static, Option<Queue>> {
    QUEUE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner())
}
fn path(root: &Path) -> PathBuf {
    crate::paths::user_data(root).join("train_queue.json")
}
fn save(q: &Queue) -> Result<(), String> {
    let p = path(&q.root);
    let tmp = p.with_extension("json.tmp");
    std::fs::create_dir_all(p.parent().unwrap()).map_err(|e| e.to_string())?;
    let bytes = serde_json::to_vec_pretty(q).map_err(|e| e.to_string())?;
    use std::io::Write;
    let mut file = std::fs::File::create(&tmp).map_err(|e| e.to_string())?;
    file.write_all(&bytes)
        .and_then(|_| file.sync_all())
        .map_err(|e| e.to_string())?;
    drop(file);
    std::fs::rename(tmp, p).map_err(|e| e.to_string())
}
fn recover(q: &mut Queue) {
    for j in &mut q.jobs {
        j.state = match j.state {
            State::Running | State::Cancelling => State::Interrupted,
            State::Queued => State::Paused,
            _ => j.state.clone(),
        };
    }
    q.dispatching = false;
}
fn load<'a>(slot: &'a mut Option<Queue>, root: &Path) -> Result<&'a mut Queue, String> {
    if slot.is_none() {
        let mut q: Queue = match std::fs::read(path(root)) {
            Ok(bytes) => serde_json::from_slice(&bytes).map_err(|e| e.to_string())?,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Queue::default(),
            Err(e) => return Err(e.to_string()),
        };
        q.root = root.into();
        recover(&mut q);
        *slot = Some(q);
    }
    Ok(slot.as_mut().unwrap())
}
fn view(q: &Queue) -> Value {
    json!({"waiting_for_realtime": q.jobs.iter().any(|j| j.state == State::Queued) && train::realtime_active(&q.root), "jobs": q.jobs.iter().map(|j| json!({
        "id": j.id, "req": j.req, "state": j.state,
        "progress": j.progress, "error": j.error, "result": j.result,
    })).collect::<Vec<_>>()})
}
fn publish(app: &AppHandle, q: &Queue) {
    let _ = app.emit("train-queue", view(q));
}
pub fn list(root: &Path) -> Result<Value, String> {
    Ok(view(load(&mut lock(), root)?))
}

fn conflict(q: &Queue, req: &TrainReq, except: Option<&str>) -> bool {
    let id = req.exp.trim().trim_end_matches(['.', ' ']).to_lowercase();
    q.jobs.iter().any(|j| {
        Some(j.id.as_str()) != except
            && j.state.active()
            && j.req.exp.trim().trim_end_matches(['.', ' ']).to_lowercase() == id
    })
}
pub fn enqueue(app: AppHandle, root: PathBuf, mut req: TrainReq) -> Result<Value, String> {
    req.exp = req.exp.trim().to_owned();
    req.output_dir = train::normalize_output_dir(&req.output_dir)?;
    train::preflight(&root, &req)?;
    let device = train::train_device(&root).to_owned();
    let result;
    {
        let mut slot = lock();
        let q = load(&mut slot, &root)?;
        if conflict(q, &req, None) {
            return Err(crate::i18n::t("trainingQueue.Conflict"));
        }
        let before = q.clone();
        q.next_id += 1;
        q.jobs.push(Job {
            id: q.next_id.to_string(),
            req,
            state: State::Queued,
            progress: Value::Null,
            error: String::new(),
            result: Value::Null,
            device,
        });
        if let Err(e) = save(q) {
            *q = before;
            return Err(e);
        }
        result = view(q);
        publish(&app, q);
    }
    dispatch(app, root);
    Ok(result)
}
fn change(q: &mut Queue, id: &str, action: &str) -> Result<bool, String> {
    if action == "clear" {
        q.jobs.retain(|j| !j.state.terminal());
        return Ok(false);
    }
    let Some(index) = q.jobs.iter().position(|j| j.id == id) else {
        return Err(crate::i18n::t("trainingQueue.Missing"));
    };
    match action {
        "remove" if !matches!(q.jobs[index].state, State::Running | State::Cancelling) => {
            q.jobs.remove(index);
        }
        "cancel" if matches!(q.jobs[index].state, State::Running | State::Cancelling) => {
            q.jobs[index].state = State::Cancelling;
            return Ok(true);
        }
        "cancel" if matches!(q.jobs[index].state, State::Queued | State::Paused) => {
            q.jobs[index].state = State::Cancelled;
        }
        "retry" if q.jobs[index].state.terminal() || q.jobs[index].state == State::Paused => {
            if conflict(q, &q.jobs[index].req, Some(id)) {
                return Err(crate::i18n::t("trainingQueue.Conflict"));
            }
            let mut job = q.jobs.remove(index);
            job.state = State::Queued;
            job.progress = Value::Null;
            job.error.clear();
            job.result = Value::Null;
            q.jobs.push(job);
        }
        _ => return Err(crate::i18n::t("trainingQueue.Changed")),
    }
    Ok(false)
}
pub fn action(app: AppHandle, root: PathBuf, id: String, action: String) -> Result<Value, String> {
    let result;
    {
        let mut slot = lock();
        let q = load(&mut slot, &root)?;
        let before = q.clone();
        let cancel = change(q, &id, &action)?;
        if let Err(e) = save(q) {
            *q = before;
            return Err(e);
        }
        // Hold the queue lock until cancellation is delivered, so the dispatcher cannot
        // advance to the next job and have this request kill that new process instead.
        if cancel {
            train::cancel_queued(&id);
        }
        result = view(q);
        publish(&app, q);
    }
    dispatch(app, root);
    Ok(result)
}
pub(crate) fn cancelled(id: &str) -> bool {
    lock().as_ref().is_some_and(|q| {
        q.jobs
            .iter()
            .any(|j| j.id == id && j.state == State::Cancelling)
    })
}
pub(crate) fn progress(app: &AppHandle, id: &str, value: &Value) {
    // The worker's env/checkpoint lines do not replace the current readable stage.
    if value["phase"] != "stage" && value["phase"] != "skip" && value["phase"] != "error" {
        return;
    }
    let mut slot = lock();
    if let Some(q) = slot.as_mut() {
        if let Some(job) = q.jobs.iter_mut().find(|j| j.id == id) {
            if value["phase"] == "error" {
                // Preserve the last stage and the worker error code when run() adds
                // its final translated error sentence.
                if let (Some(previous), Some(error)) =
                    (job.progress.as_object_mut(), value.as_object())
                {
                    previous.extend(error.clone());
                } else {
                    job.progress = value.clone();
                }
            } else {
                job.progress = value.clone();
            }
        }
        // Each worker stage/epoch is small; atomic replacement preserves restart progress.
        if let Err(e) = save(q) {
            crate::logging::shell_log!("training queue save: {}", e);
        }
        publish(app, q);
    }
}
fn claim(q: &mut Queue) -> Option<Job> {
    if q.jobs
        .iter()
        .any(|j| matches!(j.state, State::Running | State::Cancelling))
    {
        return None;
    }
    let job = q.jobs.iter_mut().find(|j| j.state == State::Queued)?;
    job.state = State::Running;
    Some(job.clone())
}
fn dispatch(app: AppHandle, root: PathBuf) {
    {
        let mut slot = lock();
        let Some(q) = slot.as_mut() else { return };
        if q.dispatching || !q.jobs.iter().any(|j| j.state == State::Queued) {
            return;
        }
        q.dispatching = true;
    }
    tauri::async_runtime::spawn_blocking(move || loop {
        {
            let mut slot = lock();
            let q = slot.as_mut().unwrap();
            if !q.jobs.iter().any(|j| j.state == State::Queued) {
                q.dispatching = false;
                return;
            }
        }
        // Preserve live audio and direct/API training. The queue never stops them.
        if train::busy() || train::realtime_active(&root) {
            std::thread::sleep(std::time::Duration::from_millis(250));
            continue;
        }
        let job = {
            let mut slot = lock();
            let q = slot.as_mut().unwrap();
            let Some(job) = claim(q) else {
                q.dispatching = false;
                return;
            };
            if let Err(e) = save(q) {
                if let Some(j) = q.jobs.iter_mut().find(|j| j.id == job.id) {
                    j.state = State::Paused;
                    j.error = e;
                }
                q.dispatching = false;
                publish(&app, q);
                return;
            }
            publish(&app, q);
            job
        };
        let result = train::run_queued(
            &app,
            &root,
            job.req.clone(),
            Some(&job.id),
            Some(&job.device),
        );
        let mut slot = lock();
        let q = slot.as_mut().unwrap();
        if let Some(j) = q.jobs.iter_mut().find(|j| j.id == job.id) {
            match result {
                Ok(result) => {
                    j.state = State::Completed;
                    j.result = result;
                }
                Err(error) => {
                    j.state = if j.state == State::Cancelling
                        || error == crate::i18n::t("s.a5ffdc95ee")
                    {
                        State::Cancelled
                    } else {
                        State::Failed
                    };
                    j.error = error;
                }
            }
        }
        if let Err(e) = save(q) {
            crate::logging::shell_log!("training queue save: {}", e);
            q.dispatching = false;
            publish(&app, q);
            return;
        }
        publish(&app, q);
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    fn job(id: &str, state: State) -> Job {
        Job {
            id: id.into(),
            state,
            req: TrainReq {
                exp: format!("role{id}"),
                dataset: "dataset".into(),
                sample_rate: "48k".into(),
                total_epoch: 200,
                batch_size: 4,
                save_every: 5,
                f0_method: "rmvpe".into(),
                save_every_weights: true,
                resume: true,
                output_dir: String::new(),
            },
            progress: Value::Null,
            error: String::new(),
            result: Value::Null,
            device: "cpu".into(),
        }
    }
    #[test]
    fn restart_never_resumes_gpu_work_automatically() {
        let mut q = Queue {
            jobs: vec![
                job("1", State::Running),
                job("2", State::Queued),
                job("3", State::Completed),
                job("4", State::Cancelling),
            ],
            ..Default::default()
        };
        recover(&mut q);
        assert_eq!(
            q.jobs.iter().map(|j| j.state.clone()).collect::<Vec<_>>(),
            vec![
                State::Interrupted,
                State::Paused,
                State::Completed,
                State::Interrupted
            ]
        );
        assert!(claim(&mut q).is_none());
    }
    #[test]
    fn claims_are_serial_and_retry_preserves_parameters() {
        let mut q = Queue {
            jobs: vec![job("1", State::Queued), job("2", State::Queued)],
            ..Default::default()
        };
        let first = claim(&mut q).unwrap();
        assert_eq!(first.id, "1");
        assert!(claim(&mut q).is_none());
        assert!(change(&mut q, "1", "remove").is_err());
        assert!(change(&mut q, "1", "cancel").unwrap());
        q.jobs[0].state = State::Cancelled;
        change(&mut q, "1", "retry").unwrap();
        assert_eq!(claim(&mut q).unwrap().id, "2");
        assert_eq!(
            serde_json::to_value(&q.jobs[1].req).unwrap(),
            serde_json::to_value(first.req).unwrap()
        );
    }
    #[test]
    fn removing_waiting_and_clearing_finished_spares_running() {
        let mut q = Queue {
            jobs: vec![
                job("1", State::Running),
                job("2", State::Queued),
                job("3", State::Completed),
            ],
            ..Default::default()
        };
        change(&mut q, "2", "remove").unwrap();
        change(&mut q, "", "clear").unwrap();
        assert_eq!(q.jobs.len(), 1);
        assert_eq!(q.jobs[0].id, "1");
    }
    #[test]
    fn request_and_device_survive_source_edits_and_restart() {
        let root = crate::testutil::scratch("training-queue-snapshot");
        std::fs::create_dir_all(&root).unwrap();
        let original = job("1", State::Queued);
        let mut draft = original.req.clone();
        let q = Queue {
            jobs: vec![original],
            root: root.clone(),
            next_id: 1,
            ..Default::default()
        };
        save(&q).unwrap();
        draft.total_epoch = 500;
        draft.dataset = "another dataset".into();
        let mut slot = None;
        let restored = load(&mut slot, &root).unwrap();
        assert_eq!(restored.jobs[0].state, State::Paused);
        assert_eq!(restored.jobs[0].device, "cpu");
        assert_eq!(restored.jobs[0].req.total_epoch, 200);
        assert_ne!(restored.jobs[0].req.dataset, draft.dataset);
        let _ = std::fs::remove_dir_all(&root);
    }
    #[test]
    fn cancellation_keeps_the_running_slot_until_the_owner_exits() {
        let mut q = Queue {
            jobs: vec![job("1", State::Running), job("2", State::Queued)],
            ..Default::default()
        };
        assert!(change(&mut q, "1", "cancel").unwrap());
        assert_eq!(q.jobs[0].state, State::Cancelling);
        assert!(claim(&mut q).is_none());
        assert!(!change(&mut q, "2", "cancel").unwrap());
        assert_eq!(q.jobs[1].state, State::Cancelled);
    }
    #[test]
    fn persistence_failure_is_reported() {
        let root = crate::testutil::scratch("training-queue-save-failure");
        std::fs::create_dir_all(&root).unwrap();
        let destination = path(&root);
        std::fs::create_dir_all(&destination).unwrap();
        let q = Queue {
            root: root.clone(),
            ..Default::default()
        };
        assert!(
            save(&q).is_err(),
            "a blocked destination cannot acknowledge a queue update"
        );
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn pending_output_collisions_are_rejected() {
        let q = Queue {
            jobs: vec![job("1", State::Queued)],
            ..Default::default()
        };
        let mut req = job("2", State::Queued).req;
        req.exp = "ROLE1".into();
        assert!(conflict(&q, &req, None));
        assert!(!conflict(&q, &req, Some("1")));
    }
}
