//! 撕裂检测与自动降级。
//!
//! 撕裂（滋滋啦啦、断断续续）的直接原因是**输出欠载**：推理没在一个块的时间
//! 内交出结果，播放指针追上了写指针，那一段音频无论如何都补不回来。
//!
//! 判据用**欠载增速**而不是 `infer_ms`。单看 infer_ms 会被偶发尖峰骗到 ——
//! 显卡被别的程序抢一下、驱动打个嗝，都会让某一块特别慢，但听感上没事。
//! 持续欠载才是真跟不上。
//!
//! 处置分两级，第二级要问过用户（改块长要停流重开，音频会断一两秒）：
//!
//! | 档 | 动作 | 打断 |
//! |---|---|---|
//! | 1 | f0 方法 rmvpe → fcpe（热参数，不重启） | 无 |
//! | 2 | block_time 抬一档 | 停流重开 |
//!
//! 有一件事这里**做不到**，写清楚免得下次有人拿它当权威：欠载只说明「没跟上」，
//! 不说明「为什么没跟上」。WASAPI 独占被抢、USB 麦掉包、笔记本降频，看起来
//! 都一样。所以第一级的文案说的是「显卡性能/资源不足」而不是「你的显卡不行」，
//! 第二级干脆只描述现象（「检测到声音撕裂」）再问一句。

/// 判定窗口。太短会被一次偶发卡顿触发，太长则用户已经难受了半天。
pub const WINDOW_SEC: f64 = 5.0;

/// 窗口内欠载超过这个比例才算「持续跟不上」。
///
/// 块长 0.25s 时 5 秒窗口约 20 块，10% 即 2 次。一次是偶发，两次开始有听感。
pub const RATE: f64 = 0.10;

/// 降过一档之后的冷却期。没有它会在一个窗口里连降到底 —— 第一级刚生效，
/// 效果还没反映到欠载计数上，就被判了第二次。
pub const COOLDOWN_SEC: f64 = 15.0;

/// f0 方法的开销排序（贵 → 便宜）。降级就是沿着这条链往下走一格。
pub const F0_LADDER: &[&str] = &["harvest", "rmvpe", "fcpe", "pm"];

/// block_time 的阶梯，单位秒。不无限往上加：超过 0.4 秒的延迟已经没法对话了，
/// 再撕裂也只能让用户自己去查设备。
pub const BLOCK_LADDER: &[f64] = &[0.25, 0.30, 0.40];

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Action {
    /// 什么都不做。
    None,
    /// 降 f0 精度。热更新，不打断。
    LowerF0,
    /// 建议放宽块长。**只是建议** —— 要停流重开，得用户点头。
    AskBlock,
}

/// 一次判定所需的全部输入。刻意做成纯数据，好在没有音频设备的机器上测。
#[derive(Debug, Clone)]
pub struct Sample {
    /// 窗口内新增的欠载次数。
    pub underruns: u32,
    /// 窗口内一共过了多少块。
    pub blocks: u32,
    /// 距离上次降级过了多久。从没降过传一个大数。
    pub since_last_action_sec: f64,
    /// 当前 f0 方法。
    pub f0: String,
    /// 当前块长。
    pub block_time: f64,
}

/// 下一步该做什么。
pub fn decide(s: &Sample) -> Action {
    if s.blocks == 0 {
        return Action::None;
    }
    if s.since_last_action_sec < COOLDOWN_SEC {
        return Action::None;
    }
    let rate = f64::from(s.underruns) / f64::from(s.blocks);
    if rate < RATE {
        return Action::None;
    }
    // 先走不打断的那一级。f0 已经到底了才谈动块长。
    if next_f0(&s.f0).is_some() {
        Action::LowerF0
    } else if next_block(s.block_time).is_some() {
        Action::AskBlock
    } else {
        // 两级都到底还在撕裂，再降就只是把声音弄得更差而不解决问题。
        Action::None
    }
}

/// 链上的下一个 f0 方法。已经是最便宜的（或者不认识）就返回 None。
pub fn next_f0(cur: &str) -> Option<&'static str> {
    let i = F0_LADDER.iter().position(|m| *m == cur)?;
    F0_LADDER.get(i + 1).copied()
}

/// 下一档块长。找不到当前档时取第一个比它大的 —— 用户手动设过怪值也能往上走。
pub fn next_block(cur: f64) -> Option<f64> {
    BLOCK_LADDER.iter().copied().find(|v| *v > cur + 1e-6)
}

// ---------------------------------------------------------------------------
// 跨心跳的状态
// ---------------------------------------------------------------------------

use std::sync::Mutex;
use std::time::Instant;

struct Watch {
    /// 上一次看到的累计欠载数。心跳报的是累计值，我们要的是增量。
    last_underrun: u32,
    /// 窗口开始的时间点和当时的欠载数。
    window_start: Instant,
    window_underrun: u32,
    /// 上次真正动手的时间。
    last_action: Option<Instant>,
}

static WATCH: Mutex<Option<Watch>> = Mutex::new(None);

/// 起播时清干净。不清的话上一段会话的欠载会算进这一段，换了台机器/换了参数
/// 之后第一个窗口就被误判。
pub fn reset() {
    if let Ok(mut g) = WATCH.lock() {
        *g = None;
    }
}

/// 喂一次心跳，拿回该做什么。
///
/// `underrun_total` 是累计值；块数按窗口时长和块长推算 —— worker 不单独报块数，
/// 而这两个数算出来的结果一样准。
pub fn step(underrun_total: u32, f0: &str, block_time: f64) -> Action {
    let mut g = match WATCH.lock() {
        Ok(g) => g,
        Err(e) => e.into_inner(),
    };
    let now = Instant::now();
    let w = g.get_or_insert(Watch {
        last_underrun: underrun_total,
        window_start: now,
        window_underrun: 0,
        last_action: None,
    });

    // 计数器只会往上走。变小说明 worker 重启了，重新开始数。
    if underrun_total < w.last_underrun {
        w.last_underrun = underrun_total;
        w.window_start = now;
        w.window_underrun = 0;
        return Action::None;
    }
    w.window_underrun += underrun_total - w.last_underrun;
    w.last_underrun = underrun_total;

    let elapsed = now.duration_since(w.window_start).as_secs_f64();
    if elapsed < WINDOW_SEC {
        return Action::None;
    }

    let bt = if block_time > 1e-3 { block_time } else { 0.25 };
    let blocks = (elapsed / bt).floor().max(0.0) as u32;
    let since = w
        .last_action
        .map(|t| now.duration_since(t).as_secs_f64())
        .unwrap_or(f64::MAX);

    let act = decide(&Sample {
        underruns: w.window_underrun,
        blocks,
        since_last_action_sec: since,
        f0: f0.to_string(),
        block_time: bt,
    });

    // 窗口滚动。无论判没判出来都要滚 —— 不滚的话旧的欠载会一直累加，
    // 一次卡顿能在后面每个窗口里反复触发。
    w.window_start = now;
    w.window_underrun = 0;
    if act != Action::None {
        w.last_action = Some(now);
    }
    act
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s(underruns: u32, blocks: u32, since: f64, f0: &str, bt: f64) -> Sample {
        Sample {
            underruns,
            blocks,
            since_last_action_sec: since,
            f0: f0.to_string(),
            block_time: bt,
        }
    }

    /// 偶发一次不该动。用户开个游戏、切个窗口都会让某一块变慢，为这个改音质
    /// 是本末倒置。
    #[test]
    fn a_single_hiccup_is_not_tearing() {
        assert_eq!(decide(&s(1, 20, 999.0, "rmvpe", 0.25)), Action::None);
    }

    #[test]
    fn sustained_underruns_lower_the_f0_method_first() {
        // 不打断的那一级必须排在前面：能不断音就不断音。
        assert_eq!(decide(&s(3, 20, 999.0, "rmvpe", 0.25)), Action::LowerF0);
    }

    /// f0 到底了才谈动块长 —— 那一步要停流重开，代价高得多。
    #[test]
    fn only_after_f0_bottoms_out_do_we_ask_about_the_block() {
        assert_eq!(decide(&s(3, 20, 999.0, "pm", 0.25)), Action::AskBlock);
        // 块长也到顶：再降只是把声音弄差，不解决问题。
        assert_eq!(decide(&s(9, 20, 999.0, "pm", 0.40)), Action::None);
    }

    /// 冷却期内一律不动。没有它会在一个窗口里连降到底：第一级刚生效，效果
    /// 还没反映到欠载计数上就被判了第二次，用户眼里是「音质突然掉了两档」。
    #[test]
    fn nothing_happens_during_the_cooldown() {
        assert_eq!(decide(&s(9, 20, 1.0, "rmvpe", 0.25)), Action::None);
        assert_eq!(decide(&s(9, 20, COOLDOWN_SEC + 0.1, "rmvpe", 0.25)), Action::LowerF0);
    }

    /// 没有块就没有判据。刚起播、或者心跳之间一块都没过时不能瞎判。
    #[test]
    fn no_blocks_means_no_verdict() {
        assert_eq!(decide(&s(0, 0, 999.0, "rmvpe", 0.25)), Action::None);
        assert_eq!(decide(&s(5, 0, 999.0, "rmvpe", 0.25)), Action::None);
    }

    #[test]
    fn the_f0_ladder_only_goes_downhill() {
        assert_eq!(next_f0("harvest"), Some("rmvpe"));
        assert_eq!(next_f0("rmvpe"), Some("fcpe"));
        assert_eq!(next_f0("fcpe"), Some("pm"));
        assert_eq!(next_f0("pm"), None);
        // 不认识的值不能瞎降 —— 用户可能配了我们不知道的方法。
        assert_eq!(next_f0("crepe"), None);
    }

    /// 计数器回退（worker 重启）不能被当成负增量。
    #[test]
    fn a_worker_restart_resets_instead_of_underflowing() {
        reset();
        assert_eq!(step(100, "rmvpe", 0.25), Action::None);
        // 100 → 3 是重启，不是「涨了负 97」。别 panic，也别乱判。
        assert_eq!(step(3, "rmvpe", 0.25), Action::None);
        reset();
    }

    #[test]
    fn an_odd_block_time_still_finds_the_next_step_up() {
        assert_eq!(next_block(0.25), Some(0.30));
        assert_eq!(next_block(0.40), None);
        // 手动设过 0.27 这种不在阶梯上的值，也要能往上走。
        assert_eq!(next_block(0.27), Some(0.30));
        assert_eq!(next_block(0.05), Some(0.25));
    }
}
