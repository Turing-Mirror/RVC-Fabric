import type { ReactNode } from "react";

/**
 * 底栏上方那条邀请式提示。
 *
 * 用在三个地方：开机查到新版本问装不装、邀请参与用户统计、变声够十次之后
 * 邀请关注。三者形状一样，语气也一样 —— 都是「问一句，随时可以不理」，
 * 不是报错也不是警告，所以没有图标、没有强调色、也不挡住任何东西。
 *
 * 「注意得到但不招摇」是靠三件事做到的，不是靠颜色：
 *
 * 1. 从底下托上来的入场动画。页面上别的东西都是静的，一个动起来的东西
 *    自然会被看到，看完就停，不循环。
 * 2. 比周围高一层的底色（--surface 而不是 --group）加一圈发丝线和一片很淡
 *    的投影 —— 视觉上浮在页面之上，但没有任何一处是亮的。
 * 3. 就这么一条，同时最多出现一个。
 *
 * 明确不做的：不闪、不跳、不用强调色铺底、不自动消失。自动消失的提示等于
 * 逼用户盯着看，而这两条消息都不值得那样对待。
 */
export function Nudge({
  title,
  children,
  actions,
}: {
  title: string;
  children: ReactNode;
  /** 右侧按钮组。第一个应该是「拒绝」，主按钮放最后，和系统对话框一致。 */
  actions: ReactNode;
}) {
  return (
    <div
      className={[
        "nudge-in mx-[30px] mb-2 max-[720px]:mx-4",
        "rounded-[var(--r)] bg-[var(--surface)] px-4 py-3",
        "shadow-[0_6px_20px_-10px_rgba(0,0,0,.3),inset_0_0_0_1px_var(--hairline)]",
        "flex items-start gap-3 flex-wrap",
      ].join(" ")}
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold mb-1">{title}</div>
        <div className="text-[12.5px] text-[var(--help)] leading-relaxed">
          {children}
        </div>
      </div>
      <div className="flex gap-2 items-center flex-wrap">{actions}</div>
    </div>
  );
}
