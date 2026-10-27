import { Component } from "@angular/core";
import { CommonModule } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { environment } from "./environment";
import { AuthService } from "./auth.service";

@Component({
  selector: "app-admin-device",
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <h2>Issue device token</h2>
    <div class="card">
      <p>
        For a device (e.g. the IOT2050 gateway) to authenticate to the MQTT
        broker. Copy the token into <code>edge/small_scope/config.js</code>'s
        <code>mqtt.deviceToken</code> — it is shown here only once.
      </p>
      <form (ngSubmit)="submit()">
        <input [(ngModel)]="email" name="email" type="email" placeholder="device email" required />
        <label class="checkbox-row">
          <input [(ngModel)]="canCommand" name="canCommand" type="checkbox" />
          Allow this device to send commands (publish to a
          <code>/command</code> topic), not just telemetry
        </label>
        <button type="submit" class="submit-btn" [disabled]="submitting">Issue token</button>
      </form>
      <p *ngIf="error" class="error-msg">{{ error }}</p>
      <div *ngIf="issuedToken" class="issued-token">
        <p class="issued-label">Device token (shown once — copy it now):</p>
        <code>{{ issuedToken }}</code>
        <button type="button" class="copy-btn" (click)="copyToken()">{{ copied ? "Copied!" : "Copy" }}</button>
        <p class="issued-perm">Command permission: <strong>{{ issuedCanCommand ? "allowed" : "telemetry only" }}</strong></p>
      </div>
    </div>
  `,
  styles: [`
    form { display: flex; flex-direction: column; gap: 0.75rem; margin-top: 0.75rem; align-items: flex-start; }
    .checkbox-row { display: flex; align-items: center; gap: 0.5rem; color: #a1a1aa; font-size: 0.8rem; }
    .submit-btn {
      padding: 10px 18px; border-radius: 8px; border: none;
      background: #fbbf24; color: #18181b; font-size: 13px;
      font-weight: 600; cursor: pointer;
    }
    .submit-btn:hover:not(:disabled) { background: #fcd34d; }
    .submit-btn:disabled { background: #27272a; color: #52525b; cursor: not-allowed; }
    .error-msg { background: #450a0a; border: 1px solid #7f1d1d; color: #fca5a5; padding: 10px 12px; border-radius: 8px; font-size: 13px; margin-top: 0.75rem; }
    .issued-token {
      margin-top: 1rem; display: flex; flex-direction: column; gap: 0.5rem; align-items: flex-start;
      background: #14532d; border: 1px solid #166534; border-radius: 8px; padding: 0.9rem 1rem;
    }
    .issued-label { color: #4ade80; font-size: 0.8rem; margin: 0; }
    .issued-perm { color: #86efac; font-size: 0.8rem; margin: 0; }
    .copy-btn {
      padding: 5px 12px; border-radius: 6px; border: 1px solid #166534;
      background: transparent; color: #4ade80; font-size: 0.75rem; cursor: pointer;
    }
    .copy-btn:hover { background: #166534; }
  `],
})
export class AdminDeviceComponent {
  email = "";
  canCommand = false;
  error = "";
  issuedToken = "";
  issuedCanCommand = false;
  copied = false;
  submitting = false;

  constructor(private auth: AuthService) {}

  async submit() {
    this.error = "";
    this.issuedToken = "";
    this.copied = false;
    this.submitting = true;
    try {
      const res = await fetch(`${environment.apiUrl}/api/admin/devices`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...this.auth.authHeader(),
        },
        body: JSON.stringify({ email: this.email, can_command: this.canCommand }),
      });
      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }
      const data = await res.json();
      this.issuedToken = data.device_token;
      this.issuedCanCommand = data.can_command;
    } catch (e) {
      this.error = "Could not issue a device token";
    } finally {
      this.submitting = false;
    }
  }

  async copyToken() {
    await navigator.clipboard.writeText(this.issuedToken);
    this.copied = true;
  }
}
