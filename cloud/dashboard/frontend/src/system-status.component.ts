import { Component, OnInit, OnDestroy } from "@angular/core";
import { CommonModule } from "@angular/common";
import { environment } from "./environment";

type Health = "ok" | "down" | "checking";

interface LogEntry {
  at: string;
  backend: Health;
  broker: Health;
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
        <span>Status log</span>
        <span class="close" (click)="expanded = false">x</span>
      </div>
      <div class="rows" *ngIf="log.length; else empty">
        <div class="row" *ngFor="let entry of log">
          <span class="time">{{ entry.at }}</span>
          <span class="chip" [class.ok]="entry.backend === 'ok'" [class.down]="entry.backend === 'down'">backend</span>
          <span class="chip" [class.ok]="entry.broker === 'ok'" [class.down]="entry.broker === 'down'">broker</span>
        </div>
      </div>
      <ng-template #empty><div class="rows empty-msg">No checks yet</div></ng-template>
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
    }
    .dot.ok { background: #4ade80; }
    .dot.down { background: #f87171; }
    .panel {
      margin-top: 0.5rem;
      width: 260px;
      max-height: 320px;
      overflow-y: auto;
      background: #09090b;
      border: 1px solid #27272a;
      border-radius: 10px;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid #27272a;
      color: #71717a;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-size: 0.65rem;
    }
    .close {
      cursor: pointer;
      color: #52525b;
    }
    .close:hover { color: #a1a1aa; }
    .rows { padding: 0.25rem 0; }
    .empty-msg { padding: 0.75rem; color: #52525b; }
    .row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.35rem 0.75rem;
    }
    .time {
      font-family: ui-monospace, monospace;
      color: #52525b;
      flex: 1;
    }
    .chip {
      border-radius: 6px;
      padding: 0.1rem 0.4rem;
      background: #27272a;
      color: #71717a;
    }
    .chip.ok { background: #14532d; color: #4ade80; }
    .chip.down { background: #450a0a; color: #f87171; }
  `],
})
export class SystemStatusComponent implements OnInit, OnDestroy {
  expanded = false;
  overall: Health = "checking";
  log: LogEntry[] = [];
  private timer?: ReturnType<typeof setInterval>;

  ngOnInit() {
    this.poll();
    this.timer = setInterval(() => this.poll(), 20000);
  }

  ngOnDestroy() {
    if (this.timer) clearInterval(this.timer);
  }

  private async poll() {
    let backend: Health = "down";
    let broker: Health = "down";
    try {
      const res = await fetch(`${environment.apiUrl}/api/health`);
      if (res.ok) {
        const data = await res.json();
        backend = data.backend === "up" ? "ok" : "down";
        broker = data.broker === "up" ? "ok" : "down";
      }
    } catch {
      backend = "down";
      broker = "down";
    }
    this.overall = backend === "ok" && broker === "ok" ? "ok" : "down";
    this.log = [{ at: new Date().toLocaleTimeString(), backend, broker }, ...this.log].slice(0, 20);
  }
}
