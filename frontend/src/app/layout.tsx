import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "whileisleep", template: "%s | whileisleep" },
  description: "Open-source customer chat with an AI agent that answers from your own data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
