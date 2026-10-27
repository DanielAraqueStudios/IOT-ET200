import { Component, OnInit, OnDestroy } from "@angular/core";
import { CommonModule } from "@angular/common";
import { environment } from "./environment";
import { AuthService } from "./auth.service";
import { LoginComponent } from "./login.component";
import { AdminDeviceComponent } from "./admin-device.component";
import { SystemStatusComponent } from "./system-status.component";

interface TagState {
  tag_name: string;
  value: string;
  updated_at: string;
}

type CommandStatus = "idle" | "pending" | "done" | "error";

@Component({
  selector: "app-dashboard",
  standalone: true,
  imports: [CommonModule, LoginComponent, AdminDeviceComponent, SystemStatusComponent],
  template: `
    <app-system-status></app-system-status>
    <app-login *ngIf="!loggedIn" (loggedIn)="onLoggedIn()"></app-login>
    <ng-container *ngIf="loggedIn">
      <h1>PLC remote control</h1>
      <div class="body">
        <section class="catalog">
          <h2 class="section-title">Tag state</h2>
          <div class="grid">
            <div class="card" *ngFor="let row of tags">
              <div class="swatch" [class.on]="isOn(row.value)" [class.off]="!isOn(row.value)"></div>
              <div class="info">
                <div class="name">{{ row.tag_name }}</div>
                <div class="val">{{ row.value }}</div>
                <div class="ts">{{ row.updated_at }}</div>
              </div>
            </div>
            <div class="empty" *ngIf="!tags.length">No tag data yet...</div>
          </div>
        </section>
        <aside class="sidebar">
          <div class="preview" [class.on]="outputOn" [class.off]="!outputOn">
            <span class="preview-label">{{ outputOn ? "ON" : "OFF" }}</span>
          </div>
          <h2 class="colorname">Output command</h2>
          <p class="hint">Publishes directly to the gateway's command topic
            (no interlock — the physical control panel can override this,
            and vice versa).</p>
          <div class="btn-row">
            <button class="cmd-btn on-btn" [disabled]="sending" (click)="sendCommand('ON')">ON</button>
            <button class="cmd-btn off-btn" [disabled]="sending" (click)="sendCommand('OFF')">OFF</button>
          </div>
          <div class="status-line" [class]="commandStatus">
            <span *ngIf="commandStatus === 'idle'">No command sent yet</span>
            <span *ngIf="commandStatus === 'pending'">Sending {{ pendingValue }}...</span>
            <span *ngIf="commandStatus === 'done'">✔ {{ lastValue }} sent to {{ lastTopic }}</span>
            <span *ngIf="commandStatus === 'error'">✘ {{ commandError }}</span>
          </div>
        </aside>
      </div>
      <app-admin-device></app-admin-device>
    </ng-container>
  `,
  styles: [`
    h1 { font-size: 20px; color: #f4f4f5; margin: 0 0 16px; }
    .body { display: flex; gap: 0; border: 1px solid #27272a; border-radius: 12px; overflow: hidden; }
    .catalog { flex: 1; padding: 24px; }
    .section-title { font-size: 14px; color: #71717a; margin: 0 0 16px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
    .empty { color: #52525b; font-size: 13px; }
    .card { border-radius: 12px; border: 1px solid #27272a; overflow: hidden; }
    .swatch { height: 40px; width: 100%; background: #27272a; }
    .swatch.on { background: #14532d; }
    .swatch.off { background: #450a0a; }
    .info { padding: 8px; background: #18181b; }
    .name { font-size: 12px; color: #f4f4f5; font-family: ui-monospace, monospace; word-break: break-all; }
    .val { font-size: 13px; color: #fbbf24; font-weight: 600; margin-top: 2px; }
    .ts { font-size: 10px; color: #52525b; margin-top: 2px; }
    .sidebar {
      width: 280px; flex-shrink: 0;
      border-left: 1px solid #27272a;
      padding: 24px;
      display: flex; flex-direction: column; gap: 16px;
      background: #09090b;
    }
    .preview {
      width: 100%; height: 96px; border-radius: 12px;
      display: flex; align-items: center; justify-content: center;
      background: #27272a; transition: background 0.3s;
    }
    .preview.on { background: #14532d; }
    .preview.off { background: #450a0a; }
    .preview-label { font-size: 22px; font-weight: 700; color: #f4f4f5; letter-spacing: 0.05em; }
    .colorname { font-size: 18px; margin: 0; color: #f4f4f5; }
    .hint { font-size: 12px; color: #71717a; margin: 0; line-height: 1.5; }
    .btn-row { display: flex; gap: 10px; }
    .cmd-btn {
      flex: 1; padding: 12px; border-radius: 10px; border: none;
      font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.15s;
    }
    .cmd-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .on-btn { background: #4ade80; color: #052e16; }
    .on-btn:hover:not(:disabled) { background: #86efac; }
    .off-btn { background: #f87171; color: #450a0a; }
    .off-btn:hover:not(:disabled) { background: #fca5a5; }
    .status-line { font-size: 12px; min-height: 16px; }
    .status-line.idle { color: #52525b; }
    .status-line.pending { color: #fbbf24; }
    .status-line.done { color: #4ade80; }
    .status-line.error { color: #f87171; }

    @media (max-width: 768px) {
      .body { flex-direction: column; }
      .sidebar { width: 100%; border-left: none; border-top: 1px solid #27272a; }
    }
  `],
})
export class DashboardComponent implements OnInit, OnDestroy {
  tags: TagState[] = [];
  loggedIn = false;
  outputOn = false;
  sending = false;
  commandStatus: CommandStatus = "idle";
  pendingValue = "";
  lastValue = "";
  lastTopic = "";
  commandError = "";
  private timer?: ReturnType<typeof setInterval>;

  constructor(private auth: AuthService) {}

  ngOnInit() {
    this.loggedIn = this.auth.isLoggedIn();
    if (this.loggedIn) {
      this.startPolling();
    }
  }

  ngOnDestroy() {
    if (this.timer) clearInterval(this.timer);
  }

  onLoggedIn() {
    this.loggedIn = true;
    this.startPolling();
  }

  isOn(value: string): boolean {
    return value === "ON" || value === "1" || value === "true";
  }

  private startPolling() {
    this.poll();
    this.timer = setInterval(() => this.poll(), 2000);
  }

  private async poll() {
    const res = await fetch(`${environment.apiUrl}/api/state`, {
      headers: this.auth.authHeader(),
    });
    if (res.status === 401) {
      this.auth.logout();
      this.loggedIn = false;
      if (this.timer) clearInterval(this.timer);
      return;
    }
    this.tags = await res.json();
    const output = this.tags.find((t) => t.tag_name.endsWith("/output/state"));
    if (output) this.outputOn = this.isOn(output.value);
  }

  async sendCommand(value: "ON" | "OFF") {
    this.sending = true;
    this.commandStatus = "pending";
    this.pendingValue = value;
    this.commandError = "";
    try {
      const res = await fetch(`${environment.apiUrl}/api/command`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...this.auth.authHeader(),
        },
        body: JSON.stringify({ value }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      const data = await res.json();
      this.lastValue = data.value;
      this.lastTopic = data.topic;
      this.commandStatus = "done";
    } catch (e: any) {
      this.commandStatus = "error";
      this.commandError = e?.message || "Could not send command";
    } finally {
      this.sending = false;
    }
  }
}
