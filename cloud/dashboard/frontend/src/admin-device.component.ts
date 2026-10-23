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
    <p>
      For a device (e.g. the IOT2050 gateway) to authenticate to the MQTT
      broker. Copy the token into <code>edge/small_scope/config.js</code>'s
      <code>mqtt.deviceToken</code> — it is shown here only once.
    </p>
    <form (ngSubmit)="submit()">
      <input [(ngModel)]="email" name="email" type="email" placeholder="device email" required />
      <button type="submit" [disabled]="submitting">Issue token</button>
    </form>
    <p *ngIf="error" class="error">{{ error }}</p>
    <div *ngIf="issuedToken" class="issued-token">
      <p><strong>Device token (shown once — copy it now):</strong></p>
      <code>{{ issuedToken }}</code>
      <button type="button" (click)="copyToken()">{{ copied ? "Copied!" : "Copy" }}</button>
    </div>
  `,
})
export class AdminDeviceComponent {
  email = "";
  error = "";
  issuedToken = "";
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
        body: JSON.stringify({ email: this.email }),
      });
      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }
      const data = await res.json();
      this.issuedToken = data.device_token;
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
