import "./globals.css";
import "./fidelity-final.css";


export const metadata = {
  title: "中医知识图谱",
  description: "中医方药知识图谱问答工作台",
};


// 前端入口布局负责加载全局样式与页面元信息。
export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
