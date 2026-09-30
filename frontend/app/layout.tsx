import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Praxis Chatbot",
  description: "P1 + D3: agente com tool de clima, checkpoint no Redis e sumarização",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
