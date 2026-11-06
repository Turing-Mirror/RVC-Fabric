use super::pairing::secret;
use fabric_audio::{
    format::PcmFormat,
    output::{self, Mixer, OutputStream, Track},
    resample::Converter,
};
use rtrb::{Producer, RingBuffer};
use serde_json::{json, Value};
use std::{
    io::{Read, Write},
    net::{Shutdown, TcpListener, TcpStream},
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        mpsc::{sync_channel, SyncSender},
        Arc,
    },
    time::{Duration, Instant},
};

pub const RATE: u32 = 48000;
pub const FRAME: usize = 960;
pub struct EngineInput {
    pub descriptor: Value,
    sender: SyncSender<Vec<u8>>,
    queued: Arc<AtomicUsize>,
    stop: Arc<AtomicBool>,
}
impl Drop for EngineInput {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
    }
}
impl EngineInput {
    pub fn send(&self, bytes: Vec<u8>) -> bool {
        self.queued.fetch_add(1, Ordering::AcqRel);
        if self.sender.try_send(bytes).is_ok() {
            true
        } else {
            self.queued.fetch_sub(1, Ordering::AcqRel);
            false
        }
    }
    pub fn queued_ms(&self) -> usize {
        self.queued.load(Ordering::Acquire) * FRAME * 1000 / RATE as usize
    }
    pub fn create(output: Arc<dyn Fn(Vec<u8>) + Send + Sync>) -> Result<Self, String> {
        let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
        listener.set_nonblocking(true).map_err(|e| e.to_string())?;
        let token = secret();
        let descriptor =
            json!({"port":listener.local_addr().map_err(|e|e.to_string())?.port(),"token":token});
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let (sender, receiver) = sync_channel::<Vec<u8>>(100);
        let queued = Arc::new(AtomicUsize::new(0));
        let pending = queued.clone();
        std::thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(180);
            while !stopping.load(Ordering::Acquire) && Instant::now() < deadline {
                if let Ok((mut stream, _)) = listener.accept() {
                    // Windows inherits the listening socket's nonblocking mode.
                    if stream.set_nonblocking(false).is_err() {
                        continue;
                    }
                    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
                    let mut hello = vec![0; token.len() + 1];
                    if stream.read_exact(&mut hello).is_err()
                        || hello != format!("{token}\n").as_bytes()
                    {
                        continue;
                    }
                    let _ = stream.set_nodelay(true);
                    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
                    let Ok(mut writer) = stream.try_clone() else {
                        break;
                    };
                    let halted = stopping.clone();
                    let pump = std::thread::spawn(move || {
                        while !halted.load(Ordering::Acquire) {
                            match receiver.recv_timeout(Duration::from_millis(100)) {
                                Ok(bytes) => {
                                    pending.fetch_sub(1, Ordering::AcqRel);
                                    if writer.write_all(&bytes).is_err() {
                                        break;
                                    }
                                }
                                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => continue,
                                Err(_) => break,
                            }
                        }
                        let _ = writer.shutdown(Shutdown::Both);
                    });
                    read_output(&mut stream, &stopping, &output);
                    stopping.store(true, Ordering::Release);
                    let _ = stream.shutdown(Shutdown::Both);
                    let _ = pump.join();
                    break;
                }
                std::thread::sleep(Duration::from_millis(20));
            }
        });
        Ok(Self {
            descriptor,
            sender,
            stop,
            queued,
        })
    }
}
fn read_output(
    stream: &mut TcpStream,
    stop: &AtomicBool,
    output: &Arc<dyn Fn(Vec<u8>) + Send + Sync>,
) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(120)));
    while !stop.load(Ordering::Acquire) {
        let mut size = [0; 4];
        if stream.read_exact(&mut size).is_err() {
            break;
        }
        let size = u32::from_be_bytes(size) as usize;
        if size == 0 || size > RATE as usize * 4 || size % 2 != 0 {
            break;
        }
        let mut pcm = vec![0; size];
        if stream.read_exact(&mut pcm).is_err() {
            break;
        }
        if !stop.load(Ordering::Acquire) {
            output(pcm);
        }
    }
}
pub struct Monitor {
    _stream: OutputStream,
    producer: Producer<f32>,
    converter: Converter,
}
impl Monitor {
    pub fn open(id: &str) -> Result<Self, String> {
        let format = output::device_format(id)?;
        let (producer, consumer) = RingBuffer::new(format.samples_for(2.0)?);
        let (track, _) = Track::new(consumer, None);
        let stream = output::open(id, Mixer::new(format, vec![track])?)?;
        let converter = Converter::new(
            PcmFormat {
                sample_rate: RATE,
                channels: 1,
            },
            format,
        )?;
        Ok(Self {
            _stream: stream,
            producer,
            converter,
        })
    }
    pub fn write(&mut self, pcm: &[f32]) {
        self.converter.process(pcm, |frame| {
            if self.producer.slots() >= frame.len() {
                for sample in frame {
                    let _ = self.producer.push(*sample);
                }
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pcm_transport_is_framed_and_stops_on_drop() {
        let (tx, rx) = std::sync::mpsc::channel();
        let input = EngineInput::create(Arc::new(move |bytes| {
            let _ = tx.send(bytes);
        }))
        .unwrap();
        let mut socket = TcpStream::connect((
            "127.0.0.1",
            input.descriptor["port"].as_u64().unwrap() as u16,
        ))
        .unwrap();
        socket
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        socket
            .write_all(format!("{}\n", input.descriptor["token"].as_str().unwrap()).as_bytes())
            .unwrap();
        assert!(input.send(vec![3; FRAME * 2]));
        let mut pcm = vec![0; FRAME * 2];
        socket.read_exact(&mut pcm).unwrap();
        assert_eq!(pcm, vec![3; FRAME * 2]);
        let length = (FRAME as u32 * 2).to_be_bytes();
        socket.write_all(&length[..1]).unwrap();
        socket.write_all(&length[1..]).unwrap();
        socket.write_all(&pcm).unwrap();
        assert_eq!(rx.recv_timeout(Duration::from_secs(3)).unwrap(), pcm);
        assert_eq!(input.queued_ms(), 0);
        drop(input);
        assert_eq!(socket.read(&mut [0]).unwrap(), 0);
    }
}
