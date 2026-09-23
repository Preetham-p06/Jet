import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Providers } from "@/components/providers";
import { AmbientBackground } from "@/components/landing/ambient-background";
import { CursorGlow } from "@/components/landing/cursor-glow";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
const TITLE = "JetStream AI — Quote Intelligence for Private Aviation";
const DESCRIPTION =
  "Turn messy charter operator quotes into clear, comparable decisions with JetStream AI.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  applicationName: "JetStream AI",
  openGraph: {
    type: "website",
    siteName: "JetStream AI",
    title: TITLE,
    description: DESCRIPTION,
    url: "/",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
  },
};

export const viewport: Viewport = {
  themeColor: "#080B10",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="relative flex min-h-full flex-col bg-bg text-fg">
        <Providers>
          <a href="#main" className="skip-link">
            Skip to content
          </a>
          <AmbientBackground />
          <CursorGlow />
          {children}
        </Providers>
      </body>
    </html>
  );
}
