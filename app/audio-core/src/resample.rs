//! Streaming sample-rate and channel conversion for monitoring, where a few
//! samples of interpolation error matter less than never blocking.
use crate::format::PcmFormat;

pub struct Converter {
    source: PcmFormat,
    target: PcmFormat,
    /// Source frames advanced per target frame.
    step: f64,
    /// Position of the next target frame, relative to `previous`.
    position: f64,
    /// Last source frame of the previous chunk, already mapped to target channels.
    previous: Vec<f32>,
    current: Vec<f32>,
    primed: bool,
}

impl Converter {
    pub fn new(source: PcmFormat, target: PcmFormat) -> Result<Self, String> {
        source.validate()?;
        target.validate()?;
        let channels = target.channels as usize;
        Ok(Self {
            source,
            target,
            step: source.sample_rate as f64 / target.sample_rate as f64,
            position: 0.0,
            previous: vec![0.0; channels],
            current: vec![0.0; channels],
            primed: false,
        })
    }

    pub fn target(&self) -> PcmFormat {
        self.target
    }

    /// Mono spreads to every channel, many-to-mono averages, otherwise channels
    /// map by index and missing ones repeat the last source channel.
    fn map_channels(&self, frame: &[f32], out: &mut [f32]) {
        let source = frame.len();
        if source == 1 {
            out.fill(frame[0]);
        } else if out.len() == 1 {
            out[0] = frame.iter().sum::<f32>() / source as f32;
        } else {
            for (index, value) in out.iter_mut().enumerate() {
                *value = frame[index.min(source - 1)];
            }
        }
    }

    /// Convert interleaved source samples; every produced target frame is handed
    /// to `emit`. State carries across calls, so chunk boundaries are seamless.
    pub fn process(&mut self, input: &[f32], mut emit: impl FnMut(&[f32])) {
        let source_channels = self.source.channels as usize;
        let channels = self.target.channels as usize;
        let mut out = vec![0.0f32; channels];
        for frame in input.chunks_exact(source_channels) {
            let mut mapped = std::mem::take(&mut self.current);
            self.map_channels(frame, &mut mapped);
            self.current = mapped;
            if !self.primed {
                // A target frame needs the source frame after it; output lags one frame.
                self.previous.copy_from_slice(&self.current);
                self.primed = true;
                self.position = 0.0;
                continue;
            }
            // Emit every target frame that falls between `previous` (0) and `current` (1).
            while self.position < 1.0 {
                let t = self.position as f32;
                for ((value, a), b) in out.iter_mut().zip(&self.previous).zip(&self.current) {
                    *value = a + (b - a) * t;
                }
                emit(&out);
                self.position += self.step;
            }
            self.position -= 1.0;
            self.previous.copy_from_slice(&self.current);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(source: PcmFormat, target: PcmFormat, chunks: &[&[f32]]) -> Vec<f32> {
        let mut converter = Converter::new(source, target).unwrap();
        let mut out = Vec::new();
        for chunk in chunks {
            converter.process(chunk, |frame| out.extend_from_slice(frame));
        }
        out
    }

    const fn fmt(sample_rate: u32, channels: u16) -> PcmFormat {
        PcmFormat {
            sample_rate,
            channels,
        }
    }

    #[test]
    fn same_format_passes_through_one_frame_behind() {
        let input = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6];
        assert_eq!(run(fmt(48000, 2), fmt(48000, 2), &[&input]), input[..4]);
    }

    #[test]
    fn halving_the_rate_keeps_every_other_frame() {
        let input: Vec<f32> = (0..8).map(|i| i as f32).collect();
        assert_eq!(run(fmt(48000, 1), fmt(24000, 1), &[&input]), [0.0, 2.0, 4.0, 6.0]);
    }

    #[test]
    fn upsampling_interpolates_between_frames() {
        let out = run(fmt(24000, 1), fmt(48000, 1), &[&[0.0, 1.0, 2.0]]);
        assert_eq!(out, [0.0, 0.5, 1.0, 1.5]);
    }

    #[test]
    fn mono_spreads_and_stereo_averages() {
        assert_eq!(run(fmt(48000, 1), fmt(48000, 2), &[&[0.5, 0.0]]), [0.5, 0.5]);
        assert_eq!(run(fmt(48000, 2), fmt(48000, 1), &[&[0.2, 0.4, 0.0, 0.0]]), [0.3f32]);
    }

    #[test]
    fn chunk_boundaries_do_not_change_the_output() {
        let input: Vec<f32> = (0..30).map(|i| (i as f32 * 0.37).sin()).collect();
        let whole = run(fmt(44100, 1), fmt(48000, 1), &[&input]);
        let split = run(fmt(44100, 1), fmt(48000, 1), &[&input[..7], &input[7..19], &input[19..]]);
        assert_eq!(whole, split);
        // 30 source frames at 44.1k span about 32.6 target frames at 48k.
        assert!((32..=33).contains(&whole.len()), "{}", whole.len());
    }
}
