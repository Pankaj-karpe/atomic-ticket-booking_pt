"use client";

import "@/globals.css";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { ToastProvider } from "@/components/ui/Toast";

function NavBar() {
  const router = useRouter();
  const { token, email, role, logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const canManage = role === "seller" || role === "admin";

  return (
    <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-lg font-bold text-white">
          🎟️ TicketEngine
        </Link>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/events" className="text-slate-300 hover:text-white">
            Events
          </Link>
          {token && (
            <Link href="/orders" className="text-slate-300 hover:text-white">
              My Orders
            </Link>
          )}
          {token && canManage && (
            <>
              <Link href="/venues" className="text-slate-300 hover:text-white">
                Venues
              </Link>
              <Link href="/events/create" className="text-slate-300 hover:text-white">
                New Event
              </Link>
            </>
          )}
          {token && role === "admin" && (
            <Link href="/admin/dashboard" className="text-slate-300 hover:text-white">
              Admin
            </Link>
          )}
          {token ? (
            <div className="flex items-center gap-3">
              <span className="hidden text-slate-500 sm:inline">{email}</span>
              <button onClick={handleLogout} className="btn-secondary py-1.5 text-xs">
                Log out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link href="/login" className="btn-secondary py-1.5 text-xs">
                Log in
              </Link>
              <Link href="/signup" className="btn-primary py-1.5 text-xs">
                Sign up
              </Link>
            </div>
          )}
        </div>
      </nav>
    </header>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <title>TicketEngine — Real-Time Seat Booking</title>
        <meta name="description" content="Real-time event ticketing and seat reservation" />
      </head>
      <body className="min-h-screen bg-slate-950">
        <ToastProvider>
          <NavBar />
          <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
        </ToastProvider>
      </body>
    </html>
  );
}
