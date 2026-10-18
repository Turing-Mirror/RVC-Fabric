//! Layout contract for the bounded microphone PCM bridge shared with Python.
//! The transport is a named mapping; this module only defines the bytes.

use crate::format::PcmFormat;

pub const HEADER_BYTES: usize = 64;
pub const MAGIC: &[u8; 8] = b"FABPCM01";
pub const VERSION: u32 = 1;
pub const WRITE_FRAME_OFFSET: usize = 32;
pub const READ_FRAME_OFFSET: usize = 40;

/// Inference publishes a whole block at once. Keep that burst in the bridge,
/// then pace the output ring so the local monitor sees playback, not a burst.
#[derive(Clone, Copy, Debug)]
pub struct MicrophoneBuffering {
    pub capacity_frames: u32,
    pub max_lag_frames: u32,
    read_ahead_frames: usize,
}

impl MicrophoneBuffering {
    pub fn for_block(format: PcmFormat, block_seconds: f64) -> Result<Self, String> {
        const BLOCK_ROUNDING_SECONDS: f64 = 0.01;
        const BACKLOG_SECONDS: f64 = 0.4;
        const MIN_BRIDGE_SECONDS: f64 = 1.0;
        const READ_AHEAD_SECONDS: f64 = 0.03;
        let frames = PcmFormat {
            channels: 1,
            ..format
        };
        frames.samples_for(block_seconds)?;
        // Workers round blocks to 10 ms. A normal block is not stale backlog.
        let max_lag_seconds = block_seconds + BLOCK_ROUNDING_SECONDS + BACKLOG_SECONDS;
        let capacity_frames =
            frames.samples_for((2.0 * max_lag_seconds).max(MIN_BRIDGE_SECONDS))?;
        let max_lag_frames = frames.samples_for(max_lag_seconds)?;
        Ok(Self {
            capacity_frames: capacity_frames.try_into().map_err(|_| "buffer_too_large")?,
            max_lag_frames: max_lag_frames.try_into().map_err(|_| "buffer_too_large")?,
            read_ahead_frames: frames.samples_for(READ_AHEAD_SECONDS)?,
        })
    }

    /// Leave the rest of an inference burst in shared memory until playback
    /// advances. This stays below the monitor's independent clock-drift budget.
    pub fn read_frames(self, queued_frames: usize, free_frames: usize) -> usize {
        const CHUNK_FRAMES: usize = 1024;
        self.read_ahead_frames
            .saturating_sub(queued_frames)
            .min(free_frames)
            .min(CHUNK_FRAMES)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Header {
    pub format: PcmFormat,
    pub capacity_frames: u32,
    pub epoch: u64,
}

impl Header {
    pub fn byte_len(self) -> Result<usize, String> {
        self.format.validate()?;
        if self.capacity_frames == 0 || self.epoch == 0 {
            return Err("invalid_pcm_bridge_header".into());
        }
        (self.capacity_frames as usize)
            .checked_mul(self.format.channels as usize)
            .and_then(|samples| samples.checked_mul(std::mem::size_of::<f32>()))
            .and_then(|bytes| bytes.checked_add(HEADER_BYTES))
            .ok_or_else(|| "invalid_pcm_bridge_size".into())
    }

    pub fn write_to(self, bytes: &mut [u8]) -> Result<(), String> {
        if bytes.len() < self.byte_len()? {
            return Err("pcm_bridge_buffer_too_small".into());
        }
        bytes[..HEADER_BYTES].fill(0);
        bytes[..8].copy_from_slice(MAGIC);
        bytes[8..12].copy_from_slice(&VERSION.to_le_bytes());
        bytes[12..16].copy_from_slice(&self.capacity_frames.to_le_bytes());
        bytes[16..20].copy_from_slice(&self.format.sample_rate.to_le_bytes());
        bytes[20..22].copy_from_slice(&self.format.channels.to_le_bytes());
        bytes[24..32].copy_from_slice(&self.epoch.to_le_bytes());
        Ok(())
    }

    pub fn read_from(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() < HEADER_BYTES || &bytes[..8] != MAGIC {
            return Err("invalid_pcm_bridge_magic".into());
        }
        if u32::from_le_bytes(bytes[8..12].try_into().unwrap()) != VERSION {
            return Err("invalid_pcm_bridge_version".into());
        }
        let header = Self {
            capacity_frames: u32::from_le_bytes(bytes[12..16].try_into().unwrap()),
            format: PcmFormat {
                sample_rate: u32::from_le_bytes(bytes[16..20].try_into().unwrap()),
                channels: u16::from_le_bytes(bytes[20..22].try_into().unwrap()),
            },
            epoch: u64::from_le_bytes(bytes[24..32].try_into().unwrap()),
        };
        if bytes.len() < header.byte_len()? {
            return Err("pcm_bridge_buffer_too_small".into());
        }
        Ok(header)
    }

    /// At most two contiguous pieces, expressed as frame index and frame count.
    pub fn segments(self, first_frame: u64, frames: u32) -> Result<[(u32, u32); 2], String> {
        if frames > self.capacity_frames {
            return Err("pcm_bridge_block_too_large".into());
        }
        let start = (first_frame % self.capacity_frames as u64) as u32;
        let head = frames.min(self.capacity_frames - start);
        Ok([(start, head), (0, frames - head)])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn microphone_buffering_accepts_every_supported_block_duration() {
        for sample_rate in [44_100, 48_000] {
            for block_seconds in [0.02, 0.06, 0.07, 0.28, 0.58, 1.13, 1.5] {
                let format = PcmFormat {
                    sample_rate,
                    channels: 2,
                };
                let buffering = MicrophoneBuffering::for_block(format, block_seconds).unwrap();
                let block_frames = (sample_rate as f64 * block_seconds).ceil() as u32;
                assert!(buffering.max_lag_frames >= block_frames);
                assert!(buffering.capacity_frames >= 2 * buffering.max_lag_frames - 1);
                let ahead = buffering.read_ahead_frames;
                assert!(ahead < format.samples_for(0.06).unwrap() / 2);
                assert_eq!(buffering.read_frames(ahead, 4096), 0);
                assert_eq!(buffering.read_frames(ahead - 1, 4096), 1);
                assert_eq!(buffering.read_frames(0, 32), 32);
            }
        }
    }

    #[test]
    fn header_round_trip_matches_the_python_layout() {
        let header = Header {
            format: PcmFormat {
                sample_rate: 48_000,
                channels: 2,
            },
            capacity_frames: 96_000,
            epoch: 17,
        };
        let mut data = vec![0u8; header.byte_len().unwrap()];
        header.write_to(&mut data).unwrap();
        assert_eq!(&data[..8], b"FABPCM01");
        assert_eq!(&data[12..16], &96_000u32.to_le_bytes());
        assert_eq!(&data[24..32], &17u64.to_le_bytes());
        assert_eq!(Header::read_from(&data).unwrap(), header);
        assert_eq!(header.segments(95_998, 4).unwrap(), [(95_998, 2), (0, 2)]);
    }

    #[test]
    fn rejects_bad_header_and_oversized_blocks() {
        let header = Header {
            format: PcmFormat {
                sample_rate: 48_000,
                channels: 2,
            },
            capacity_frames: 4,
            epoch: 1,
        };
        let mut data = vec![0u8; header.byte_len().unwrap()];
        header.write_to(&mut data).unwrap();
        data[8] = 2;
        assert!(Header::read_from(&data).is_err());
        assert!(header.segments(0, 5).is_err());
    }
}
