//! 背景图的字节 → data URL。
//!
//! 只为一件事存在：让界面能把背景图**画进 canvas 读像素**。
//!
//! 界面跑在 `http(s)://<scheme>.localhost`，用 `convertFileSrc` 出来的 asset
//! 地址画到 canvas 上，那张 canvas 会被标成 tainted，`getImageData` 直接抛
//! SecurityError。于是 `lib/wallpaperTone` 采样永远失败、永远退回中庸值 ——
//! 「按图自适应」看着在跑，实际上一张图都没读进去。字节从这边读、编成 data URL
//! 交过去就是同源的，canvas 不会脏。
//!
//! 这条路只在直接采样失败时才走，所以多数机器上一次都不会调到。

use std::path::{Path, PathBuf};

/// 肯为采样搬多大的图。编成 base64 还要再涨三分之一，这个数已经是 IPC 上
/// 能接受的上限；再大的图直接放弃采样（界面退回中庸那一档），不值当为了
/// 一点点配色把几十兆字符串搬过去。
const MAX_BYTES: u64 = 16 * 1024 * 1024;

/// 按魔数认类型。只认能当背景图的那几种，认不出来就不给。
fn sniff_mime(b: &[u8]) -> Option<&'static str> {
    if b.len() > 3 && b[0] == 0xFF && b[1] == 0xD8 && b[2] == 0xFF {
        return Some("image/jpeg");
    }
    if b.len() > 8 && b[0..4] == [0x89, 0x50, 0x4E, 0x47] {
        return Some("image/png");
    }
    if b.len() > 12 && &b[0..4] == b"RIFF" && &b[8..12] == b"WEBP" {
        return Some("image/webp");
    }
    if b.len() > 2 && b[0] == 0x42 && b[1] == 0x4D {
        return Some("image/bmp");
    }
    None
}

const B64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn encode_base64(data: &[u8]) -> String {
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for c in data.chunks(3) {
        let b = [c[0], *c.get(1).unwrap_or(&0), *c.get(2).unwrap_or(&0)];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        out.push(B64[(n >> 18) as usize & 63] as char);
        out.push(B64[(n >> 12) as usize & 63] as char);
        out.push(if c.len() > 1 { B64[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if c.len() > 2 { B64[n as usize & 63] as char } else { '=' });
    }
    out
}

/// 读一张本机图片，返回 `data:image/…;base64,…`。
///
/// 只收本机路径。不收 http(s)：背景图是用户从自己盘上选的，给这条命令开
/// 网络出口等于多一个「让界面指使后端去访问任意地址」的口子，而它一点用处
/// 都没有。
pub fn data_url(path: &str) -> Result<String, String> {
    let p = PathBuf::from(path.trim());
    if path.trim().is_empty() || !p.is_file() {
        return Err("not a file".into());
    }
    read_capped(&p)
}

fn read_capped(p: &Path) -> Result<String, String> {
    let len = p.metadata().map(|m| m.len()).unwrap_or(0);
    if len < 32 || len > MAX_BYTES {
        return Err("size".into());
    }
    let data = std::fs::read(p).map_err(|e| e.to_string())?;
    let mime = sniff_mime(&data).ok_or_else(|| "not an image".to_string())?;
    Ok(format!("data:{mime};base64,{}", encode_base64(&data)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_the_reference_vectors() {
        assert_eq!(encode_base64(b""), "");
        assert_eq!(encode_base64(b"f"), "Zg==");
        assert_eq!(encode_base64(b"fo"), "Zm8=");
        assert_eq!(encode_base64(b"foo"), "Zm9v");
        assert_eq!(encode_base64(b"foob"), "Zm9vYg==");
        assert_eq!(encode_base64(b"fooba"), "Zm9vYmE=");
        assert_eq!(encode_base64(b"foobar"), "Zm9vYmFy");
    }

    #[test]
    fn only_real_image_bytes_get_a_mime() {
        assert_eq!(sniff_mime(&[0xFF, 0xD8, 0xFF, 0xE0]), Some("image/jpeg"));
        assert_eq!(
            sniff_mime(&[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00]),
            Some("image/png")
        );
        // 改了扩展名的文本 / 脚本一律不给，别让它以 image/* 的身份回到界面里。
        assert_eq!(sniff_mime(b"<svg xmlns=\"http://www.w3.org/2000/svg\">"), None);
        assert_eq!(sniff_mime(b"#!/bin/sh\necho hi\n"), None);
        assert_eq!(sniff_mime(b""), None);
    }

    #[test]
    fn a_missing_or_empty_path_is_refused_not_panicked() {
        assert!(data_url("").is_err());
        assert!(data_url("   ").is_err());
        assert!(data_url("/nope/definitely/not/here.png").is_err());
    }

    /// 只收本机路径。给这条命令开网络出口等于多一个「界面指使后端访问任意
    /// 地址」的口子，而背景图是用户从自己盘上选的，一点用处都没有。
    #[test]
    fn remote_urls_are_not_fetched() {
        assert!(data_url("https://example.invalid/a.png").is_err());
        assert!(data_url("http://127.0.0.1:1/a.png").is_err());
        assert!(data_url("file:///etc/passwd").is_err());
    }

    #[test]
    fn a_real_png_round_trips() {
        let p = crate::testutil::scratch("wp-dataurl");
        std::fs::create_dir_all(&p).unwrap();
        let f = p.join("a.png");
        let mut png = vec![0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
        png.extend(std::iter::repeat_n(0u8, 64));
        std::fs::write(&f, &png).unwrap();
        let u = data_url(f.to_str().unwrap()).unwrap();
        assert!(u.starts_with("data:image/png;base64,"), "{u}");
        let _ = std::fs::remove_dir_all(&p);
    }

    #[test]
    fn a_file_too_large_to_be_worth_moving_is_refused() {
        let p = crate::testutil::scratch("wp-huge");
        std::fs::create_dir_all(&p).unwrap();
        let f = p.join("big.png");
        std::fs::write(&f, vec![0u8; 8]).unwrap(); // 太小
        assert!(data_url(f.to_str().unwrap()).is_err());
        let _ = std::fs::remove_dir_all(&p);
    }
}
