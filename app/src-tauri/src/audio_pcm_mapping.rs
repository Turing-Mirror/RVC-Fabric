//! Windows named mapping for the bounded Python-to-native microphone bridge.
//! The reader stays off CPAL's callback and copies into its own fixed ring.
use fabric_audio::pcm_bridge::{Header, HEADER_BYTES, READ_FRAME_OFFSET, WRITE_FRAME_OFFSET};
use std::{
    ffi::OsStr,
    os::windows::ffi::OsStrExt,
    ptr,
    sync::atomic::{AtomicU64, Ordering},
};
use windows_sys::Win32::{
    Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS, HANDLE, INVALID_HANDLE_VALUE},
    System::Memory::{
        CreateFileMappingW, MapViewOfFile, UnmapViewOfFile, FILE_MAP_ALL_ACCESS,
        MEMORY_MAPPED_VIEW_ADDRESS, PAGE_READWRITE,
    },
};

pub struct PcmMapping {
    handle: HANDLE,
    view: MEMORY_MAPPED_VIEW_ADDRESS,
    name: String,
    header: Header,
}

// The mapping is moved to one reader thread. Python is the only PCM writer;
// the sequence fields are cross-process atomics.
unsafe impl Send for PcmMapping {}

impl PcmMapping {
    pub fn create(header: Header) -> Result<Self, String> {
        let len = header.byte_len()?;
        let name = format!(
            "Local\\RVCFabricPcm-{}-{}",
            std::process::id(),
            header.epoch
        );
        let wide: Vec<u16> = OsStr::new(&name).encode_wide().chain([0]).collect();
        let size = len as u64;
        let handle = unsafe {
            CreateFileMappingW(
                INVALID_HANDLE_VALUE,
                ptr::null(),
                PAGE_READWRITE,
                (size >> 32) as u32,
                size as u32,
                wide.as_ptr(),
            )
        };
        if handle.is_null() {
            return Err(std::io::Error::last_os_error().to_string());
        }
        if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
            unsafe { CloseHandle(handle) };
            return Err("pcm_bridge_name_exists".into());
        }
        let view = unsafe { MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, len) };
        if view.Value.is_null() {
            let error = std::io::Error::last_os_error().to_string();
            unsafe { CloseHandle(handle) };
            return Err(error);
        }
        let bytes = unsafe { std::slice::from_raw_parts_mut(view.Value.cast::<u8>(), len) };
        if let Err(error) = header.write_to(bytes) {
            unsafe {
                UnmapViewOfFile(view);
                CloseHandle(handle);
            }
            return Err(error);
        }
        Ok(Self {
            handle,
            view,
            name,
            header,
        })
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    fn cursor(&self, offset: usize) -> &AtomicU64 {
        // Both offsets are 8-byte aligned inside a page-aligned mapping.
        unsafe { &*self.view.Value.cast::<u8>().add(offset).cast::<AtomicU64>() }
    }

    /// Copy whole frames only. Backlog beyond max_lag_frames is dropped so a
    /// delayed microphone can never build up seconds of audible latency.
    pub fn read_into(&mut self, out: &mut [f32], max_lag_frames: u32) -> Result<usize, String> {
        let channels = self.header.format.channels as usize;
        if out.len() % channels != 0
            || max_lag_frames == 0
            || max_lag_frames > self.header.capacity_frames
        {
            return Err("invalid_pcm_bridge_read".into());
        }
        let write = self.cursor(WRITE_FRAME_OFFSET).load(Ordering::Acquire);
        let mut read = self.cursor(READ_FRAME_OFFSET).load(Ordering::Acquire);
        if write < read || write - read > self.header.capacity_frames as u64 {
            return Err("invalid_pcm_bridge_cursor".into());
        }
        if write - read > max_lag_frames as u64 {
            read = write - max_lag_frames as u64;
        }
        let frames = ((write - read) as usize).min(out.len() / channels);
        let parts = self.header.segments(read, frames as u32)?;
        let data = unsafe { self.view.Value.cast::<u8>().add(HEADER_BYTES).cast::<f32>() };
        let mut dest = 0usize;
        for (start, count) in parts {
            let samples = count as usize * channels;
            if samples != 0 {
                unsafe {
                    ptr::copy_nonoverlapping(
                        data.add(start as usize * channels),
                        out.as_mut_ptr().add(dest),
                        samples,
                    );
                }
                dest += samples;
            }
        }
        self.cursor(READ_FRAME_OFFSET)
            .store(read + frames as u64, Ordering::Release);
        Ok(frames)
    }
}

impl Drop for PcmMapping {
    fn drop(&mut self) {
        unsafe {
            UnmapViewOfFile(self.view);
            CloseHandle(self.handle);
        }
    }
}
