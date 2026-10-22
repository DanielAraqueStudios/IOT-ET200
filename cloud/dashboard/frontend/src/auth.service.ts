import { Injectable } from "@angular/core";
import { environment } from "./environment";

// Token kept in sessionStorage (cleared when the tab closes) rather than
// localStorage, since this is a short-lived (1h) bearer token and
// localStorage would persist it indefinitely if never cleared.
const TOKEN_KEY = "plc_dashboard_token";

@Injectable({ providedIn: "root" })
export class AuthService {
  get token(): string | null {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  isLoggedIn(): boolean {
    return this.token !== null;
  }

  async login(username: string, password: string): Promise<void> {
    const res = await fetch(`${environment.apiUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      throw new Error("Invalid credentials");
    }
    const data = await res.json();
    sessionStorage.setItem(TOKEN_KEY, data.access_token);
  }

  logout(): void {
    sessionStorage.removeItem(TOKEN_KEY);
  }

  authHeader(): Record<string, string> {
    const token = this.token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
