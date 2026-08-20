import { t } from "../i18n/t";

/**
 * 接线图。下面那张表说的是「每一格该填什么」，这张图说的是「声音往哪走」。
 *
 * 内联 SVG 而不是打包图片：颜色全部走 CSS 变量，明暗主题各自成立，也不用为
 * 一张图多带一份 PNG。文字用 `<text>` 而不是描边路径，所以它跟着 i18n 走，
 * 八个语言共用同一张图。
 *
 * 坐标写在 viewBox 里，宽高交给容器：窗口拉大缩小都等比缩放。
 */
export function RouteDiagram() {
  // 两条链路的锚点。改这里就能挪整块，不用逐个数坐标。
  const y = 46;          // 主链路（送给对方）
  const yMon = 116;      // 监听支路（自己听）
  const boxW = 116;
  const boxH = 40;
  const xs = [8, 168, 328, 488];

  return (
    <svg
      viewBox="0 0 620 168"
      width="100%"
      height="auto"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={t("s.routeDiagramAlt")}
      className="block w-full h-auto mb-4"
    >
      <defs>
        <marker
          id="rd-arrow"
          viewBox="0 0 8 8"
          refX="7"
          refY="4"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M0 0 L8 4 L0 8 z" fill="var(--line)" />
        </marker>
      </defs>

      {/* 主链路：麦克风 → 本软件 → CABLE → 游戏 */}
      {[
        { x: xs[0], title: t("s.routeMic"), sub: t("s.routeMicSub") },
        { x: xs[1], title: t("s.routeApp"), sub: t("s.routeAppSub"), accent: true },
        { x: xs[2], title: "CABLE", sub: t("s.routeCableSub") },
        { x: xs[3], title: t("s.routeGame"), sub: t("s.routeGameSub") },
      ].map((b) => (
        <g key={b.x}>
          <rect
            x={b.x}
            y={y}
            width={boxW}
            height={boxH}
            rx="8"
            fill={b.accent ? "var(--accent-soft)" : "transparent"}
            stroke={b.accent ? "var(--accent)" : "var(--line)"}
          />
          <text
            x={b.x + boxW / 2}
            y={y + 17}
            textAnchor="middle"
            fontSize="12"
            fill="var(--ink)"
          >
            {b.title}
          </text>
          <text
            x={b.x + boxW / 2}
            y={y + 31}
            textAnchor="middle"
            fontSize="10"
            fill="var(--help)"
          >
            {b.sub}
          </text>
        </g>
      ))}
      {xs.slice(0, 3).map((x) => (
        <line
          key={x}
          x1={x + boxW + 6}
          y1={y + boxH / 2}
          x2={x + boxW + 38}
          y2={y + boxH / 2}
          stroke="var(--line)"
          strokeWidth="1.5"
          markerEnd="url(#rd-arrow)"
        />
      ))}

      {/* 监听支路：从本软件往下拐到耳机。虚线，因为它是可选的。 */}
      <path
        d={`M${xs[1] + boxW / 2} ${y + boxH + 4} V${yMon + boxH / 2} H${xs[2] - 6}`}
        fill="none"
        stroke="var(--line)"
        strokeWidth="1.5"
        strokeDasharray="4 4"
        markerEnd="url(#rd-arrow)"
      />
      <rect
        x={xs[2]}
        y={yMon}
        width={boxW}
        height={boxH}
        rx="8"
        fill="transparent"
        stroke="var(--line)"
        strokeDasharray="4 4"
      />
      <text x={xs[2] + boxW / 2} y={yMon + 17} textAnchor="middle" fontSize="12" fill="var(--ink)">
        {t("s.routeMonitor")}
      </text>
      <text x={xs[2] + boxW / 2} y={yMon + 31} textAnchor="middle" fontSize="10" fill="var(--help)">
        {t("s.routeMonitorSub")}
      </text>
      <text x={xs[3] + 4} y={yMon + 24} fontSize="10" fill="var(--meta)">
        {t("s.routeMonitorNote")}
      </text>
    </svg>
  );
}
