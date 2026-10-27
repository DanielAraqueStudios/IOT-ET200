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
        <button type="submit" [disabled]="submitting">Issue token</button>
      </form>
      <p *ngIf="error" class="error">{{ error }}</p>
      <div *ngIf="issuedToken" class="issued-token">
        <p><strong>Device token (shown once — copy it now):</strong></p>
        <code>{{ issuedToken }}</code>
        <button type="button" (click)="copyToken()">{{ copied ? "Copied!" : "Copy" }}</button>
        <p>Command permission: <strong>{{ issuedCanCommand ? "allowed" : "telemetry only" }}</strong></p>
      </div>
    </div>
  `,
  styles: [`
    form { display: flex; flex-direction: column; gap: 0.75rem; margin-top: 0.75rem; align-items: flex-start; }
    .checkbox-row { display: flex; align-items: center; gap: 0.5rem; color: #a1a1aa; font-size: 0.8rem; }
    .issued-token { margin-top: 1rem; display: flex; flex-direction: column; gap: 0.5rem; align-items: flex-start; }
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
