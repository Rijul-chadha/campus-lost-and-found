import type { Metadata } from "next";
import { Atkinson_Hyperlegible, Bricolage_Grotesque } from "next/font/google";
import type { ReactNode } from "react";

import { TopBar } from "@/components/TopBar";
import { SessionProvider } from "@/lib/session";

import "./globals.css";

const display = Bricolage_Grotesque({
  subsets: ["latin"], weight: ["600", "700", "800"], variable: "--font-bricolage",
});
const body = Atkinson_Hyperlegible({
  subsets: ["latin"], weight: ["400", "700"], variable: "--font-atkinson",
});

export const metadata: Metadata = {
  title: "Campus Lost & Found",
  description: "Report what you found. Find what you lost.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <SessionProvider>
          <TopBar />
          <main className="wrap">{children}</main>
        </SessionProvider>
      </body>
    </html>
  );
}
