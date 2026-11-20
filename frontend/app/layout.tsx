import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BONE-MAP · Bone Architecture & Recovery Platform",
  description:
    "AI-assisted bone architecture quantification, longitudinal CT/X-ray tracking, and physiotherapy recovery monitoring.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}>
      <body className="min-h-full bg-[#F5F5F7] text-[#1D1D1F] selection:bg-[#0071E3]/15 selection:text-[#0071E3]">
        {children}
      </body>
    </html>
  );
}
