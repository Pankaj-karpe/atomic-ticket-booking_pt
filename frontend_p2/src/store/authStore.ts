"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserRole } from "@/types";

interface DecodedToken {
  user_id: number;
  role: UserRole;
  exp: number;
}

// Decodes the JWT payload CLIENT-SIDE, without verifying the signature —
// that's fine here, since we're only reading user_id/role for UI purposes
// (which links, which pages to show). Every real authorization decision
// still happens on the backend, which verifies the signature properly.
function decodeJwt(token: string): DecodedToken | null {
  try {
    const payload = token.split(".")[1];
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
        .join("")
    );
    return JSON.parse(json) as DecodedToken;
  } catch {
    return null;
  }
}

interface AuthState {
  token: string | null;
  userId: number | null;
  role: UserRole | null;
  email: string | null;
  setSession: (token: string, email: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      userId: null,
      role: null,
      email: null,
      setSession: (token, email) => {
        const decoded = decodeJwt(token);
        set({
          token,
          email,
          userId: decoded?.user_id ?? null,
          role: decoded?.role ?? null,
        });
      },
      logout: () => set({ token: null, userId: null, role: null, email: null }),
    }),
    { name: "ticketing-auth" }
  )
);
