import type { Metadata } from "next"
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google"

import { TopBar } from "@/components/top-bar"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"

import "./globals.css"

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] })
const spaceGrotesk = Space_Grotesk({ variable: "--font-space-grotesk", subsets: ["latin"] })
const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"] })

export const metadata: Metadata = {
  title: "Black Box",
  description: "Flight recorder for AI agents. Record, blame, fork, prove.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`dark ${inter.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <TooltipProvider>
          <TopBar />
          {children}
          <Toaster theme="dark" position="bottom-right" richColors />
        </TooltipProvider>
      </body>
    </html>
  )
}
