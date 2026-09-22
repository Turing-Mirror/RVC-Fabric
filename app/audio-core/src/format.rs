use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct PcmFormat {
    pub sample_rate: u32,
    pub channels: u16,
}
impl PcmFormat {
    pub fn validate(self) -> Result<Self, String> {
        if self.sample_rate == 0 || self.channels == 0 {
            return Err("invalid_pcm_format".into());
        }
        Ok(self)
    }
    pub fn samples_for(self, seconds: f64) -> Result<usize, String> {
        self.validate()?;
        if !seconds.is_finite() || seconds <= 0.0 {
            return Err("invalid_buffer_duration".into());
        }
        let frames = (seconds * self.sample_rate as f64).ceil();
        if frames >= (usize::MAX / self.channels as usize) as f64 {
            return Err("buffer_too_large".into());
        }
        Ok(frames as usize * self.channels as usize)
    }
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct ClipRange {
    pub start: f64,
    pub end: Option<f64>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FrameRange {
    pub start: u64,
    pub end: u64,
}
impl ClipRange {
    pub fn resolve(self, duration: f64, sample_rate: u32) -> Result<FrameRange, String> {
        let end = self.end.unwrap_or(duration);
        if sample_rate == 0
            || !duration.is_finite()
            || duration <= 0.0
            || !self.start.is_finite()
            || !end.is_finite()
            || self.start < 0.0
            || end > duration
            || self.start >= end
            || duration * sample_rate as f64 >= u64::MAX as f64
        {
            return Err("invalid_clip_range".into());
        }
        // Half-open interval: include sample timestamps >= start and < end.
        let frames = FrameRange {
            start: (self.start * sample_rate as f64).ceil() as u64,
            end: (end * sample_rate as f64).ceil() as u64,
        };
        if frames.start >= frames.end {
            return Err("empty_clip_range".into());
        }
        Ok(frames)
    }
}
impl FrameRange {
    pub fn frames(self) -> u64 {
        self.end - self.start
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn range_is_half_open_and_defaults_to_end() {
        assert_eq!(
            ClipRange {
                start: 0.25,
                end: None
            }
            .resolve(1.0, 48000)
            .unwrap(),
            FrameRange {
                start: 12000,
                end: 48000
            }
        );
        assert_eq!(
            ClipRange {
                start: 0.11,
                end: Some(0.29)
            }
            .resolve(1.0, 10)
            .unwrap(),
            FrameRange { start: 2, end: 3 }
        );
    }
    #[test]
    fn rejects_invalid_ranges() {
        for r in [
            ClipRange {
                start: -1.0,
                end: None,
            },
            ClipRange {
                start: f64::NAN,
                end: None,
            },
            ClipRange {
                start: 0.0,
                end: Some(f64::INFINITY),
            },
            ClipRange {
                start: 0.5,
                end: Some(0.5),
            },
            ClipRange {
                start: 0.0,
                end: Some(1.1),
            },
        ] {
            assert!(r.resolve(1.0, 48000).is_err());
        }
        assert!(ClipRange::default().resolve(f64::NAN, 48000).is_err());
        assert!(ClipRange::default().resolve(1.0, 0).is_err());
    }
    #[test]
    fn buffer_is_whole_frames() {
        assert_eq!(
            PcmFormat {
                sample_rate: 48000,
                channels: 2
            }
            .samples_for(0.25)
            .unwrap(),
            24000
        );
        assert!(PcmFormat {
            sample_rate: 0,
            channels: 2
        }
        .samples_for(1.0)
        .is_err());
    }
}
