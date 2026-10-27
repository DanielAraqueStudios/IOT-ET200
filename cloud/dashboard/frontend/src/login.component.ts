import { Component, EventEmitter, Output } from "@angular/core";
import { CommonModule } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { AuthService } from "./auth.service";

@Component({
  selector: "app-login",
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page">
      <div class="card">
        <h1 class="brand">PLC <span class="accent">Dashboard</span></h1>
        <p class="tagline">Operations console</p>
        <form (ngSubmit)="submit()">
          <label>
            <span>Username</span>
            <input [(ngModel)]="username" name="username" placeholder="admin" required autocomplete="username" />
          </label>
          <label>
            <span>Password</span>
            <input [(ngModel)]="password" name="password" type="password" placeholder="••••••••" required autocomplete="current-password" />
          </label>
          <p class="error-msg" *ngIf="error">{{ error }}</p>
          <button type="submit" class="submit-btn">Log in</button>
        </form>
      </div>
    </div>
  `,
  styles: [`
    .page {
      min-height: 100dvh;
      display: flex; align-items: center; justify-content: center;
      padding: 16px; box-sizing: border-box;
    }
    .card {
      width: 100%; max-width: 380px; background: #18181b;
      border: 1px solid #27272a; border-radius: 16px;
      padding: 36px 32px; box-sizing: border-box;
    }
    .brand { font-size: 24px; margin: 0 0 4px; color: #f4f4f5; font-weight: 600; letter-spacing: -0.01em; }
    .accent { color: #fbbf24; font-style: italic; }
    .tagline { font-size: 11px; color: #52525b; text-transform: uppercase; letter-spacing: .12em; margin: 0 0 28px; }
    form { display: flex; flex-direction: column; gap: 16px; }
    label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #a1a1aa; }
    input {
      padding: 10px 12px; border-radius: 8px;
      border: 1px solid #27272a; background: #09090b;
      color: #f4f4f5; font-size: 14px; outline: none;
      width: 100%; box-sizing: border-box;
    }
    input:focus { border-color: #52525b; }
    .error-msg { background: #450a0a; border: 1px solid #7f1d1d; color: #fca5a5; padding: 10px 12px; border-radius: 8px; font-size: 13px; margin: 0; }
    .submit-btn {
      padding: 13px; border-radius: 10px; border: none;
      background: #fbbf24; color: #18181b; font-size: 14px;
      font-weight: 600; cursor: pointer; margin-top: 4px;
      width: 100%; box-sizing: border-box;
    }
    .submit-btn:hover { background: #fcd34d; }
    @media (max-width: 400px) {
      .card { padding: 28px 20px; border-radius: 12px; }
      .brand { font-size: 20px; }
    }
  `],
})
export class LoginComponent {
  @Output() loggedIn = new EventEmitter<void>();
  username = "";
  password = "";
  error = "";

  constructor(private auth: AuthService) {}

  async submit() {
    this.error = "";
    try {
      await this.auth.login(this.username, this.password);
      this.loggedIn.emit();
    } catch {
      this.error = "Invalid credentials";
    }
  }
}
