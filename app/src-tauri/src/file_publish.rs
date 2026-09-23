//! Publish a completed file without replacing a file that appeared meanwhile.
use std::{fs, io, path::Path};

pub(crate) fn publish_new(temp: &Path, target: &Path) -> io::Result<()> {
    match fs::hard_link(temp, target) {
        Ok(()) => {
            let _ = fs::remove_file(temp);
            Ok(())
        }
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => Err(error),
        Err(_) => {
            // Some external volumes do not allow hard links. Reserve the name first.
            let mut input = fs::File::open(temp)?;
            let mut output = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(target)?;
            let result = io::copy(&mut input, &mut output).and_then(|_| output.sync_all());
            if let Err(error) = result {
                drop(output);
                let _ = fs::remove_file(target);
                return Err(error);
            }
            let _ = fs::remove_file(temp);
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    #[test]
    fn existing_target_stays_untouched() {
        static SEQ: AtomicU64 = AtomicU64::new(0);
        let dir = std::env::temp_dir().join(format!(
            "fabric-publish-{}-{}",
            std::process::id(),
            SEQ.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&dir).unwrap();
        let temp = dir.join("temp");
        let target = dir.join("target");
        fs::write(&temp, b"new").unwrap();
        fs::write(&target, b"old").unwrap();
        assert!(publish_new(&temp, &target).is_err());
        assert_eq!(fs::read(&target).unwrap(), b"old");
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn new_target_receives_complete_file() {
        let dir = std::env::temp_dir().join(format!("fabric-publish-new-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let temp = dir.join("temp");
        let target = dir.join("target");
        fs::write(&temp, b"complete").unwrap();
        publish_new(&temp, &target).unwrap();
        assert!(!temp.exists());
        assert_eq!(fs::read(&target).unwrap(), b"complete");
        fs::remove_dir_all(dir).unwrap();
    }
}
