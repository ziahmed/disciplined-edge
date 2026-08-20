import type { ReactNode } from "react";

export const metadata = {
  title: "Disciplined Edge",
  description: "Markets reward discipline, not prediction.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
