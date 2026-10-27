import { Component, OnInit, OnDestroy } from "@angular/core";
import { CommonModule } from "@angular/common";
import { environment } from "./environment";

type Health = "ok" | "down" | "checking";

interface Check {
  label: string;
  ok: boolean | null;
  detail: string;
}

interface LogEntry {
  id: number;
  ts: string;
  level: "ok" | "warn" | "error";
  msg: string;
}

@Component({
  selector: "app-system-status",
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="widget" (click)="expanded = !expanded">
      <span class="dot" [class.ok]="overall === 'ok'" [class.down]="overall === 'down'"></span>
      <span class="label">{{ overall === "checking" ? "Checking..." : overall === "ok" ? "System OK" : "System down" }}</span>
    </div>
    <div class="panel" *ngIf="expanded">
      <div class="panel-header">
        <span class="panel-title">System status</span>
        <span class="refresh" (click)="poll()">↺</span>
      </div>
      <div class="checks">
        <div class="check" *ngFor="let c of checks">
          <span class="indicator" [style.background]="c.ok === null ? '#3f3f46' : c.ok ? '#4ade80' : '#f87171'"></span>
          <div class="check-info">
            <span class="check-label">{{ c.label }}</span>
            <span class="check-detail">{{ c.detail }}</span>
          </div>
        </div>
      </div>
      <div class="ready-badge" [class.ready]="overall === 'ok'">
        {{ overall === "ok" ? "✔ All systems go" : overall === "checking" ? "Checking..." : "⚠ Check connections" }}
      </div>
      <div class="log-header">
        <span class="panel-title">Event log</span>
        <span class="clear-btn" (click)="log = []">Clear</span>
      </div>
      <div class="log-body">
        <div class="empty" *ngIf="!log.length">No events yet...</div>
        <div class="entry" [class]="entry.level" *ngFor="let entry of log">
          <span class="ts">{{ entry.ts }}</span>
          <span class="dot-icon">{{ icons[entry.level] }}</span>
          <span class="msg">{{ entry.msg }}</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    :host {
      position: fixed;
      top: 1rem;
      right: 1rem;
      z-index: 1000;
      font-size: 0.75rem;
    }
    .widget {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      background: #18181b;
      border: 1px solid #27272a;
      border-radius: 999px;
      padding: 0.4rem 0.9rem;
      cursor: pointer;
      user-select: none;
      color: #a1a1aa;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #3f3f46;
      flex-shrink: 0;
      transition: background 0.3s;
    }
    .dot.ok { background: #4ade80; }
    .dot.down { background: #f87171; }
    .panel {
      margin-top: 0.5rem;
      width: 280px;
      max-height: 420px;
      display: flex;
      flex-direction: column;
      background: #09090b;
      border: 1px solid #27272a;
      border-radius: 10px;
      overflow: hidden;
    }
    .panel-header, .log-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 16px;
      border-bottom: 1px solid #27272a;
      flex-shrink: 0;
    }
    .log-header { border-top: 1px solid #27272a; }
    .panel-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: #52525b; }
    .refresh, .clear-btn { color: #52525b; cursor: pointer; user-select: none; }
    .refresh { font-size: 14px; }
    .clear-btn { font-size: 10px; padding: 2px 8px; border-radius: 4px; border: 1px solid #27272a; }
    .refresh:hover, .clear-btn:hover { color: #a1a1aa; border-color: #52525b; }
    .checks { padding: 8px 0; }
    .check { display: flex; align-items: center; gap: 10px; padding: 6px 16px; }
    .indicator { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .check-info { display: flex; flex-direction: column; gap: 1px; }
    .check-label { font-size: 12px; color: #e4e4e7; }
    .check-detail { font-size: 10px; color: #52525b; font-family: ui-monospace, monospace; }
    .ready-badge {
      margin: 8px 16px 12px;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 11px;
      text-align: center;
      background: #27272a;
      color: #71717a;
      transition: all 0.3s;
    }
    .ready-badge.ready { background: #14532d; color: #4ade80; }
    .log-body {
      flex: 1;
      max-height: 160px;
      overflow-y: auto;
      padding: 6px 0;
      font-family: ui-monospace, monospace;
      font-size: 11px;
      display: flex;
      flex-direction: column;
    }
    .empty { color: #3f3f46; padding: 12px 16px; }
    .entry { display: flex; align-items: baseline; gap: 8px; padding: 2px 16px; line-height: 1.6; }
    .entry:hover { background: #18181b; }
    .ts { color: #3f3f46; flex-shrink: 0; }
    .dot-icon { flex-shrink: 0; width: 12px; text-align: center; }
    .msg { color: #a1a1aa; word-break: break-word; }
    .entry.ok .msg { color: #4ade80; }
    .entry.error .msg { color: #f87171; }
    .entry.warn .msg { color: #fbbf24; }
  `],
})
export class SystemStatusComponent implements OnInit, OnDestroy {
  expanded = false;
  overall: Health = "checking";
  checks: Check[] = [
    { label: "Dashboard backend", ok: null, detail: "Checking..." },
    { label: "MQTT broker", ok: null, detail: "Checking..." },
  ];
  log: LogEntry[] = [];
  icons = { ok: "✔", warn: "⚠", error: "✘" };
  private seq = 0;
  private timer?: ReturnType<typeof setInterval>;

  ngOnInit() {
    this.poll();
    this.timer = setInterval(() => this.poll(), 20000);
  }

  ngOnDestroy() {
    if (this.timer) clearInterval(this.timer);
  }

  async poll() {
    let backendOk = false;
    let brokerOk = false;
    let backendDetail = "No response";
    let brokerDetail = "No response";
    try {
      const res = await fetch(`${environment.apiUrl}/api/health`);
      if (res.ok) {
        const data = await res.json();
        backendOk = data.backend === "up";
        brokerOk = data.broker === "up";
        backendDetail = backendOk ? "Connected" : "Down";
        brokerDetail = brokerOk ? "MQTT connected" : "Not connected";
      }
    } catch {
      backendDetail = "Unreachable";
      brokerDetail = "Unreachable";
    }
    this.setCheck(0, backendOk, backendDetail);
    this.setCheck(1, brokerOk, brokerDetail);
    this.overall = backendOk && brokerOk ? "ok" : "down";
  }

  private setCheck(i: number, ok: boolean, detail: string) {
    const prev = this.checks[i];
    if (prev.ok !== ok) {
      this.addLog(ok ? "ok" : "warn", `${prev.label}: ${detail}`);
    }
    this.checks[i] = { ...prev, ok, detail };
  }

  private addLog(level: "ok" | "warn" | "error", msg: string) {
    const now = new Date();
    const ts = now.toLocaleTimeString() + "." + String(now.getMilliseconds()).padStart(3, "0");
    this.log = [{ id: ++this.seq, ts, level, msg }, ...this.log].slice(0, 50);
  }
}
