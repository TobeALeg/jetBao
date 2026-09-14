/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        // 品牌色：雾青 Mist（低饱和，白字对比 5.37:1）
        // 用法约定：solid 只授予"当前屏唯一的实心主操作"，其余一律用 soft/line/ink
        accent: {
          DEFAULT: "#34756d",
          hover: "#2b635c",
          soft: "#eef5f4",
          line: "#c9dedb",
          ink: "#2f6f68"
        },
        surface: {
          DEFAULT: "#ffffff",
          canvas: "#f8faf9",
          soft: "#f8fafc",
          mute: "#f1f5f9"
        },
        hairline: "#e2e8f0",
        "line-strong": "#cbd5e1",
        // 状态语义：每组三件套（soft / line / ink），页面里只引用这三件套
        // 硬规则：action 只表示"需要你动手"；等审核/已归档降为 neutral/done
        state: {
          neutral: { soft: "#f1f5f9", line: "#e2e8f0", ink: "#475569" },
          action: { soft: "#eef5f4", line: "#c9dedb", ink: "#2f6f68" },
          warn: { soft: "#fffbeb", line: "#fde68a", ink: "#b45309" },
          danger: { soft: "#fff1f2", line: "#fecdd3", ink: "#be123c" },
          done: { soft: "#f8fafc", line: "#e2e8f0", ink: "#64748b" }
        }
      },
      borderRadius: {
        sm: "6px",
        control: "8px",
        panel: "14px"
      },
      boxShadow: {
        // 层级方向：面板浮起，面板内的贴片扁平
        flat: "0 0 0 1px rgba(15, 23, 42, 0.04)",
        raised: "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px -2px rgba(15, 23, 42, 0.06)",
        overlay: "0 8px 16px -4px rgba(15, 23, 42, 0.10), 0 24px 48px -12px rgba(15, 23, 42, 0.18)"
      },
      height: {
        "control-xs": "28px",
        "control-sm": "32px",
        "control-lg": "36px"
      },
      width: {
        "control-xs": "28px",
        "control-sm": "32px",
        "control-lg": "36px"
      },
      transitionDuration: {
        1: "120ms",
        2: "200ms",
        3: "320ms",
        4: "520ms"
      },
      transitionTimingFunction: {
        standard: "cubic-bezier(0.2, 0, 0, 1)",
        exit: "cubic-bezier(0.4, 0, 1, 1)",
        emphasis: "cubic-bezier(0.34, 1.36, 0.64, 1)"
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "none" }
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.97) translateY(4px)" },
          to: { opacity: "1", transform: "none" }
        },
        "dot-pulse": {
          "0%, 100%": { opacity: "0.35", transform: "scale(0.85)" },
          "50%": { opacity: "1", transform: "scale(1)" }
        },
        "pop": {
          "0%": { opacity: "0", transform: "scale(0.9)" },
          "60%": { opacity: "1", transform: "scale(1.04)" },
          "100%": { transform: "scale(1)" }
        }
      },
      animation: {
        "fade-up": "fade-up 200ms cubic-bezier(0.2, 0, 0, 1) both",
        "scale-in": "scale-in 320ms cubic-bezier(0.2, 0, 0, 1) both",
        "dot-pulse": "dot-pulse 1.6s cubic-bezier(0.2, 0, 0, 1) infinite",
        pop: "pop 520ms cubic-bezier(0.34, 1.36, 0.64, 1) both"
      }
    }
  },
  plugins: []
};
