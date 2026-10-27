import { Component, OnInit } from "@angular/core";
import { CommonModule } from "@angular/common";
import { environment } from "./environment";
import { AuthService } from "./auth.service";

interface DeviceInfo {
  email: string;
  can_command: boolean;
  enabled: boolean;
  created_at: string;
}

@Component({
  selector: "app-device-list",
  standalone: true,
  imports: [CommonModule],
  template: `
    <h2>Issued devices</h2>
    <div class="card">
      <p *ngIf="error" class="error-msg">{{ error }}</p>
      <table *ngIf="devices.length">
        <thead>
          <tr><th>Email</th><th>Command</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          <tr *ngFor="let d of devices">
            <td>{{ d.email }}</td>
            <td>{{ d.can_command ? "allowed" : "telemetry only" }}</td>
            <td>
              <span [class.status-on]="d.enabled" [class.status-off]="!d.enabled">
                {{ d.enabled ? "Enabled" : "Disabled" }}
              </span>
            </td>
            <td>
              <button
                type="button"
                class="toggle-btn"
                [class.toggle-btn-off]="d.enabled"
                [disabled]="pending === d.email"
                (click)="toggle(d)"
              >
                {{ d.enabled ? "Disable" : "Enable" }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p *ngIf="!devices.length && !error" class="empty-msg">No devices issued yet.</p>
    </div>
  `,
  styles: [`
    table { width: 100%; border-collapse: collapse; margin-top: 0.75rem; }
    th, td { text-align: left; padding: 8px 10px; font-size: 0.8rem; color: #e4e4e7; border-bottom: 1px solid #27272a; }
    th { color: #a1a1aa; font-weight: 600; }
    .status-on { color: #4ade80; }
    .status-off { color: #f87171; }
    .toggle-btn {
      padding: 5px 12px; border-radius: 6px; border: 1px solid #166534;
      background: transparent; color: #4ade80; font-size: 0.75rem; cursor: pointer;
    }
    .toggle-btn:hover:not(:disabled) { background: #166534; }
    .toggle-btn-off { border-color: #7f1d1d; color: #f87171; }
    .toggle-btn-off:hover:not(:disabled) { background: #450a0a; }
    .toggle-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .error-msg { background: #450a0a; border: 1px solid #7f1d1d; color: #fca5a5; padding: 10px 12px; border-radius: 8px; font-size: 13px; }
    .empty-msg { color: #71717a; font-size: 0.8rem; }
  `],
})
export class DeviceListComponent implements OnInit {
  devices: DeviceInfo[] = [];
  error = "";
  pending = "";

  constructor(private auth: AuthService) {}

  ngOnInit() {
    this.load();
  }

  async load() {
    this.error = "";
    try {
      const res = await fetch(`${environment.apiUrl}/api/admin/devices`, {
        headers: this.auth.authHeader(),
      });
      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }
      this.devices = await res.json();
    } catch (e) {
      this.error = "Could not load devices";
    }
  }

  async toggle(d: DeviceInfo) {
    this.pending = d.email;
    this.error = "";
    const next = !d.enabled;
    try {
      const res = await fetch(`${environment.apiUrl}/api/admin/devices/${encodeURIComponent(d.email)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...this.auth.authHeader(),
        },
        body: JSON.stringify({ enabled: next }),
      });
      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }
      const updated = await res.json();
      d.enabled = updated.enabled;
    } catch (e) {
      this.error = `Could not update ${d.email}`;
    } finally {
      this.pending = "";
    }
  }
}
